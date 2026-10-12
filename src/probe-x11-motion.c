/* SPDX-License-Identifier: MIT
 * Same gray background / moving blue bar as probe-present --motion, using
 * standard X11 PutImage and Present, without the Debian Vulkan bridge.
 */
#define _GNU_SOURCE
#include <xcb/xcb.h>
#include <xcb/present.h>
#include <sys/mman.h>
#include <poll.h>
#include <unistd.h>
#include <fcntl.h>
#include <signal.h>
#include <time.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

static volatile sig_atomic_t stopped;
static void stop(int s) { (void)s; stopped=1; }
static uint64_t now_ns(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t); return (uint64_t)t.tv_sec*1000000000+t.tv_nsec; }
struct buffer { uint32_t *pixels; xcb_pixmap_t pixmap; int busy; };
static int check(xcb_connection_t *c, xcb_void_cookie_t cookie) {
    xcb_generic_error_t *e=xcb_request_check(c,cookie);
    if (!e) return 0;
    fprintf(stderr,"X11 error=%u major=%u minor=%u\n",e->error_code,e->major_code,e->minor_code); free(e); return -1;
}
static unsigned number(const char *text) { char *end; unsigned long n=strtoul(text,&end,10); return !*text || *end || !n || n>100000 ? 0 : n; }
int main(int argc,char **argv) {
    unsigned width=640,height=480,frames=600,rate=60,idle_ms=0;
    const char *path=NULL,*events_path=NULL;
    int fullscreen=0,marker=-1;
    for (int i=1;i<argc;++i) {
        if (!strcmp(argv[i],"--width") && i+1<argc) width=number(argv[++i]);
        else if (!strcmp(argv[i],"--height") && i+1<argc) height=number(argv[++i]);
        else if (!strcmp(argv[i],"--frames") && i+1<argc) frames=number(argv[++i]);
        else if (!strcmp(argv[i],"--rate") && i+1<argc) rate=number(argv[++i]);
        else if (!strcmp(argv[i],"--idle-ms") && i+1<argc) idle_ms=number(argv[++i]);
        else if (!strcmp(argv[i],"--fullscreen")) fullscreen=1;
        else if (!strcmp(argv[i],"--markers")) marker=open("/proc/1/root/sys/kernel/tracing/trace_marker",O_WRONLY|O_CLOEXEC);
        else if (!strcmp(argv[i],"--timings") && i+1<argc) path=argv[++i];
        else if (!strcmp(argv[i],"--events") && i+1<argc) events_path=argv[++i];
        else return 64;
    }
    if (width<64 || height<32 || width>10000 || height>10000 || !frames || !rate || rate>240) return 64;
    signal(SIGINT,stop); signal(SIGTERM,stop);
    int code=1; FILE *csv=NULL,*events=NULL;
    xcb_connection_t *c=xcb_connect(NULL,NULL); xcb_window_t window=0;
    xcb_special_event_t *special=NULL;
    struct buffer buffers[4]={0}; size_t bytes=(size_t)width*height*4;
    if (xcb_connection_has_error(c)) goto done;
    xcb_screen_t *screen=xcb_setup_roots_iterator(xcb_get_setup(c)).data;
    window=xcb_generate_id(c);
    uint32_t values[]={screen->black_pixel,fullscreen};
    if (check(c,xcb_create_window_checked(c,XCB_COPY_FROM_PARENT,window,screen->root,fullscreen?0:24,fullscreen?0:120,
        width,height,0,XCB_WINDOW_CLASS_INPUT_OUTPUT,screen->root_visual,XCB_CW_BACK_PIXEL|XCB_CW_OVERRIDE_REDIRECT,values))) goto done;
    const char title[]="Controlled X11 motion";
    xcb_change_property(c,XCB_PROP_MODE_REPLACE,window,XCB_ATOM_WM_NAME,XCB_ATOM_STRING,8,sizeof(title)-1,title);
    xcb_map_window(c,window); xcb_flush(c);
    uint32_t eid=xcb_generate_id(c);
    special=xcb_register_for_special_xge(c,&xcb_present_id,eid,NULL);
    if (!special || check(c,xcb_present_select_input_checked(c,eid,window,XCB_PRESENT_EVENT_MASK_COMPLETE_NOTIFY|XCB_PRESENT_EVENT_MASK_IDLE_NOTIFY))) goto done;
    for (unsigned i=0;i<4;++i) {
        buffers[i].pixels=malloc(bytes);
        if(!buffers[i].pixels)goto done;
        buffers[i].pixmap=xcb_generate_id(c);
        if (check(c,xcb_create_pixmap_checked(c,screen->root_depth,buffers[i].pixmap,window,width,height))) goto done;
    }
    if (path) { int fd=open(path,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600); if(fd<0 || !(csv=fdopen(fd,"w")))goto done;
        fputs("cycle,frame,start_ns,acquire_us,queue_present_us,host_frame_us,due_ns,render_ready_us\n",csv); }
    if (events_path) { int fd=open(events_path,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600); if(fd<0 || !(events=fdopen(fd,"w")))goto done;
        fputs("monotonic_ns,event,serial,msc,pixmap,mode\n",events); }
    xcb_gcontext_t gc=xcb_generate_id(c);
    if(check(c,xcb_create_gc_checked(c,gc,window,0,NULL)))goto done;
    uint64_t due=now_ns(), last_msc=0;
    for (unsigned frame=0;frame<frames && !stopped;++frame) {
        struct timespec deadline={.tv_sec=due/1000000000,.tv_nsec=due%1000000000};
        while(clock_nanosleep(CLOCK_MONOTONIC,TIMER_ABSTIME,&deadline,NULL)==EINTR && !stopped) {}
        uint64_t started=now_ns(); int chosen=-1;
        do {
            xcb_generic_event_t *event;
            while ((event=xcb_poll_for_special_event(c,special))) {
                xcb_present_generic_event_t *generic=(void *)event;
                if (generic->evtype==XCB_PRESENT_EVENT_IDLE_NOTIFY) {
                    xcb_present_idle_notify_event_t *e=(void *)event;
                    for (unsigned i=0;i<4;++i) if(buffers[i].pixmap==e->pixmap) buffers[i].busy=0;
                    if(events)fprintf(events,"%llu,idle,%u,0,%u,0\n",(unsigned long long)now_ns(),e->serial,e->pixmap);
                } else if (generic->evtype==XCB_PRESENT_EVENT_COMPLETE_NOTIFY) {
                    xcb_present_complete_notify_event_t *e=(void *)event; last_msc=e->msc;
                    if(events)fprintf(events,"%llu,complete,%u,%llu,0,%u\n",(unsigned long long)now_ns(),e->serial,(unsigned long long)e->msc,e->mode);
                }
                free(event);
            }
            for (unsigned i=0;i<4;++i) if(!buffers[i].busy) {chosen=i;break;}
            if (chosen<0) {
                struct pollfd descriptor={xcb_get_file_descriptor(c),POLLIN,0};
                if (poll(&descriptor,1,100)<0 && errno!=EINTR) goto done;
                if (now_ns()-started>UINT64_C(5000000000) || xcb_connection_has_error(c)) goto done;
            }
        } while(chosen<0 && !stopped);
        if (stopped) break;
        uint64_t acquired=now_ns();
        uint32_t *pixels=buffers[chosen].pixels;
        for (size_t i=0;i<bytes/4;++i) pixels[i]=0xff333333;
        unsigned bar=(frame*8)%(width-63);
        for (unsigned y=height/4;y<height/4+height/2;++y)
            for (unsigned x=bar;x<bar+64;++x) pixels[(size_t)y*width+x]=0xff2673d9;
        uint64_t ready=now_ns();
        if(marker>=0) {char line[96];int n=snprintf(line,sizeof(line),"C|%d|PAD_FRAME|%u",getpid(),frame);(void)write(marker,line,n);}
        unsigned max_rows=(xcb_get_maximum_request_length(c)*4-128)/(width*4);
        if(!max_rows)goto done;
        for(unsigned y=0;y<height;y+=max_rows) {
            unsigned rows=height-y<max_rows?height-y:max_rows;
            xcb_put_image(c,XCB_IMAGE_FORMAT_Z_PIXMAP,buffers[chosen].pixmap,gc,width,rows,0,y,0,screen->root_depth,rows*width*4,(const uint8_t *)(pixels+(size_t)y*width));
        }
        xcb_present_pixmap(c,window,buffers[chosen].pixmap,frame+1,0,0,0,0,0,0,0,
            XCB_PRESENT_OPTION_NONE,last_msc?last_msc+1:0,0,0,0,NULL);
        xcb_flush(c); buffers[chosen].busy=1;
        if(csv)fprintf(csv,"0,%u,%llu,%.3f,%.3f,%.3f,%llu,%.3f\n",frame,(unsigned long long)started,
            (acquired-started)/1000.,(now_ns()-ready)/1000.,(now_ns()-started)/1000.,(unsigned long long)due,(ready-started)/1000.);
        due+=1000000000/rate; uint64_t current=now_ns();
        if(current>due)due+=((current-due)/(1000000000/rate)+1)*(1000000000/rate);
    }
    if(idle_ms) {struct timespec pause={.tv_sec=idle_ms/1000,.tv_nsec=(idle_ms%1000)*1000000L};while(nanosleep(&pause,&pause)&&errno==EINTR&&!stopped){}}
    puts("X11_PUTIMAGE_PRESENT_MOTION_OK"); code=0;
done:
    if(special)xcb_unregister_for_special_event(c,special);
    for(unsigned i=0;i<4;++i) { if(buffers[i].pixmap)xcb_free_pixmap(c,buffers[i].pixmap);if(buffers[i].pixels)free(buffers[i].pixels); }
    if(window)xcb_destroy_window(c,window);
    xcb_flush(c); xcb_disconnect(c);
    if(csv)fclose(csv);
    if(events)fclose(events);
    if(marker>=0)close(marker);
    return code;
}
