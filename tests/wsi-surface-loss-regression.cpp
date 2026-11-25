/* SPDX-License-Identifier: MIT
 * Candidate-only tests: compile against r3.5 plus wsi-surface-loss.patch.
 * Reuse the deterministic fixture and run all baseline tests first.
 */
#define main baseline_main
#define xcb_get_geometry_reply baseline_geometry_reply
#define xcb_request_check baseline_request_check
#include "wsi-regression.cpp"
#undef xcb_get_geometry_reply
#undef xcb_request_check
#undef main

namespace {
bool missing_geometry = false;
bool invalid_present_window = false;
unsigned checked_selects = 0;
}
extern "C" {
xcb_get_geometry_reply_t *xcb_get_geometry_reply(xcb_connection_t *c,
   xcb_get_geometry_cookie_t cookie, xcb_generic_error_t **error)
{
   return missing_geometry ? nullptr : baseline_geometry_reply(c, cookie, error);
}
xcb_void_cookie_t xcb_present_select_input_checked(xcb_connection_t *, uint32_t, xcb_window_t, uint32_t)
{
   ++checked_selects;
   return {1};
}
xcb_generic_error_t *xcb_request_check(xcb_connection_t *, xcb_void_cookie_t)
{
   if (!invalid_present_window) return nullptr;
   auto error = static_cast<xcb_generic_error_t *>(calloc(1, sizeof(xcb_generic_error_t)));
   error->error_code = XCB_WINDOW;
   return error;
}
}
int main()
{
   if (baseline_main()) return 1;
   try {
      fixture f;
      VkSurfaceCapabilitiesKHR caps{};
      missing_geometry = true;
      require(f.surface.get_properties().get_surface_capabilities(physical_handle, &caps)
                 == VK_ERROR_SURFACE_LOST_KHR, "missing geometry returned success");
      VkPhysicalDeviceSurfaceInfo2KHR info{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SURFACE_INFO_2_KHR};
      VkSurfaceCapabilities2KHR caps2{VK_STRUCTURE_TYPE_SURFACE_CAPABILITIES_2_KHR};
      require(f.surface.get_properties().get_surface_capabilities(physical_handle, &info, &caps2)
                 == VK_ERROR_SURFACE_LOST_KHR, "capabilities2 swallowed surface loss");
      missing_geometry = false;
      invalid_present_window = true;
      unsigned before = checked_selects;
      {
         auto chain = std::make_unique<wsi::x11::swapchain>(f.device, nullptr, &f.surface);
         bool use_thread = false;
         require(chain->init_platform(handle<VkDevice>(), nullptr, use_thread)
                    == VK_ERROR_SURFACE_LOST_KHR, "Present registration error returned success");
         require(!chain->m_present_event_thread.joinable() && chain->m_event_thread_wakeup_fd == -1,
                 "failed registration started an event thread");
      }
      require(checked_selects == before + 1, "registration was not checked");
      puts("WSI_SURFACE_LOSS_REGRESSION_OK");
   } catch (const std::exception &error) {
      fprintf(stderr, "surface-loss regression: %s\n", error.what());
      return 1;
   }
}
