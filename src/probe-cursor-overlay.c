/* SPDX-License-Identifier: MIT
 * Bounded cursor-only probe. Owns an override-redirect test window, never grabs
 * input/focus, and restores the pointer on normal exit, EOF, SIGINT or SIGTERM.
 * The parent controls stages through stdin; a 45-second deadline bounds failure.
 */
#define _POSIX_C_SOURCE 200809L
#include <X11/Xlib.h>
#include <X11/Xlib-xcb.h>
#include <xcb/xfixes.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
static volatile sig_atomic_t stopped, failed;
static void stop(int unused) { (void)unused; stopped=1; }
static int error(Display *d, XErrorEvent *e) {
    (void)d;
    fprintf(stderr,"X error=%u major=%u minor=%u\n",e->error_code,e->request_code,e->minor_code);
    stopped=failed=1;return 0;
}
static double now(void) { struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9; }
static Cursor square(Display *d,Window w,int width,int height,unsigned short r,unsigned short g,unsigned short b) {
    unsigned char bits[256]; memset(bits,255,sizeof(bits));
    Pixmap source=XCreateBitmapFromData(d,w,(char*)bits,width,height);
    XColor foreground={.red=r,.green=g,.blue=b},background=foreground;
    Cursor c=XCreatePixmapCursor(d,source,source,&foreground,&background,5,7);
    XFreePixmap(d,source);return c;
}
int main(void) {
    signal(SIGINT,stop);signal(SIGTERM,stop);signal(SIGPIPE,stop);
    Display *d=XOpenDisplay(NULL); if(!d)return 1;
    XSetErrorHandler(error);
    xcb_xfixes_query_version_cookie_t version=xcb_xfixes_query_version(XGetXCBConnection(d),5,0);
    xcb_xfixes_query_version_reply_t *reply=xcb_xfixes_query_version_reply(XGetXCBConnection(d),version,NULL);
    if(!reply||reply->major_version<4){free(reply);XCloseDisplay(d);return 1;}
    free(reply);
    int screen=DefaultScreen(d),width=DisplayWidth(d,screen),height=DisplayHeight(d,screen);
    Window root=RootWindow(d,screen),r,child;int oldx=0,oldy=0,wx,wy;unsigned mask;
    if(!XQueryPointer(d,root,&r,&child,&oldx,&oldy,&wx,&wy,&mask)){XCloseDisplay(d);return 1;}
    XSetWindowAttributes a={.override_redirect=True,.background_pixel=0x183040};
    Window w=XCreateWindow(d,root,0,0,width,height,0,CopyFromParent,InputOutput,CopyFromParent,CWOverrideRedirect|CWBackPixel,&a);
    XStoreName(d,w,"r3.6 cursor-only acceptance (bounded)");
    Cursor red=square(d,w,24,24,65535,0,0),blue=square(d,w,48,16,0,0,65535);
    XDefineCursor(d,w,red);XMapRaised(d,w);
    GC gc=XCreateGC(d,w,0,NULL);XSetForeground(d,gc,0xffffff);
    const char *label="r3.6 cursor-only probe: static content; no input focus or clicks";
    XDrawString(d,w,gc,80,80,label,strlen(label));XSync(d,False);
    printf("ready %lu %d %d\n",w,width,height);fflush(stdout);
    double deadline=now()+45;int hidden=0;
    while(!stopped&&now()<deadline) {
        struct pollfd p={.fd=STDIN_FILENO,.events=POLLIN};
        if(poll(&p,1,100)<=0)continue;
        char line[128];if(!fgets(line,sizeof(line),stdin))break;
        int x,y;
        if(sscanf(line,"red %d %d",&x,&y)==2||sscanf(line,"blue %d %d",&x,&y)==2) {
            if(x<40||y<40||x>width-80||y>height-80)break;
            if(hidden){xcb_xfixes_show_cursor(XGetXCBConnection(d),w);hidden=0;}
            XDefineCursor(d,w,line[0]=='r'?red:blue);XWarpPointer(d,None,w,0,0,0,0,x,y);
        } else if(!strncmp(line,"hide",4)) {if(!hidden){xcb_xfixes_hide_cursor(XGetXCBConnection(d),w);hidden=1;}}
        else if(!strncmp(line,"motion",6)) {
            double end=now()+2;unsigned n=0;
            while(!stopped&&now()<end) {
                XWarpPointer(d,None,w,0,0,0,0,100+(n*13)%(width-200),180+(n*7)%(height-300));
                XFlush(d);++n;
                struct timespec delay={.tv_nsec=8333333};nanosleep(&delay,NULL);
            }
            printf("warps %u\n",n);
        } else if(!strncmp(line,"exit",4))break;
        else break;
        XSync(d,False);
        XQueryPointer(d,root,&r,&child,&wx,&wy,&x,&y,&mask);
        printf("pointer %d %d\n",wx,wy);puts("done");fflush(stdout);
    }
    if(hidden)xcb_xfixes_show_cursor(XGetXCBConnection(d),w);
    XUndefineCursor(d,w);XDestroyWindow(d,w);XWarpPointer(d,None,root,0,0,0,0,oldx,oldy);
    XFreeCursor(d,red);XFreeCursor(d,blue);XFreeGC(d,gc);XSync(d,False);XCloseDisplay(d);
    return failed ? 1 : 0;
}
