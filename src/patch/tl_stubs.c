/*
 * TL stubs: 本构建禁用了 xwayland / x11 / drm-lease 后端，
 * 但 sway 二进制链接时要求这些符号存在。它们只会在对应后端启用时被调用，
 * 我们永远不会走到，返回 NULL/false 即可。
 */
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>


/* ---- 前置声明（满足 -Wmissing-prototypes）---- */
void *wlr_xwayland_create(void *, void *, bool);
void wlr_xwayland_destroy(void *);
void wlr_xwayland_set_seat(void *, void *);
void wlr_xwayland_set_cursor(void *, uint8_t *, uint32_t, uint32_t, uint32_t,
		int32_t, int32_t);
int wlr_xwayland_icccm_input_model(const void *);
bool wlr_xwayland_or_surface_wants_focus(const void *);
void *wlr_xwayland_surface_try_from_wlr_surface(void *);
void wlr_xwayland_surface_activate(void *, bool);
void wlr_xwayland_surface_close(void *);
void wlr_xwayland_surface_configure(void *, int32_t, int32_t, uint32_t, uint32_t);
void wlr_xwayland_surface_restack(void *, void *, int);
void wlr_xwayland_surface_set_fullscreen(void *, bool);
void wlr_xwayland_surface_set_maximized(void *, bool);
void wlr_xwayland_surface_set_minimized(void *, bool);
void *wlr_x11_output_create(void *);
bool wlr_output_is_drm(void *);
void *wlr_drm_lease_v1_manager_create(void *, void *);
bool wlr_drm_lease_v1_manager_offer_output(void *, void *);
void wlr_drm_lease_request_v1_grant(void *);
void wlr_drm_lease_request_v1_reject(void *);
bool wlr_backend_is_x11(void *);
void wlr_drm_connector_add_mode(void *, const void *);
int wlr_drm_connector_get_panel_orientation(void *);

/* ---- xwayland ---- */
void *wlr_xwayland_create(void *display, void *compositor, bool lazy) {
	(void)display; (void)compositor; (void)lazy; return NULL;
}
void wlr_xwayland_destroy(void *xwayland) { (void)xwayland; }
void wlr_xwayland_set_seat(void *xwayland, void *seat) { (void)xwayland; (void)seat; }
void wlr_xwayland_set_cursor(void *xwayland, uint8_t *pixels, uint32_t stride,
		uint32_t width, uint32_t height, int32_t hotspot_x, int32_t hotspot_y) {
	(void)xwayland; (void)pixels; (void)stride; (void)width; (void)height;
	(void)hotspot_x; (void)hotspot_y;
}
int wlr_xwayland_icccm_input_model(const void *xsurface) { (void)xsurface; return 0; }
bool wlr_xwayland_or_surface_wants_focus(const void *xsurface) { (void)xsurface; return false; }
void *wlr_xwayland_surface_try_from_wlr_surface(void *surface) { (void)surface; return NULL; }
void wlr_xwayland_surface_activate(void *xsurface, bool activated) { (void)xsurface; (void)activated; }
void wlr_xwayland_surface_close(void *xsurface) { (void)xsurface; }
void wlr_xwayland_surface_configure(void *xsurface, int32_t x, int32_t y,
		uint32_t width, uint32_t height) {
	(void)xsurface; (void)x; (void)y; (void)width; (void)height;
}
void wlr_xwayland_surface_restack(void *xsurface, void *sibling, int mode) {
	(void)xsurface; (void)sibling; (void)mode;
}
void wlr_xwayland_surface_set_fullscreen(void *xsurface, bool fs) { (void)xsurface; (void)fs; }
void wlr_xwayland_surface_set_maximized(void *xsurface, bool m) { (void)xsurface; (void)m; }
void wlr_xwayland_surface_set_minimized(void *xsurface, bool m) { (void)xsurface; (void)m; }

/* ---- x11 backend ---- */
void *wlr_x11_output_create(void *x11_backend) { (void)x11_backend; return NULL; }

/* ---- drm backend / lease ---- */
bool wlr_output_is_drm(void *output) { (void)output; return false; }
void *wlr_drm_lease_v1_manager_create(void *backend, void *client) {
	(void)backend; (void)client; return NULL;
}
bool wlr_drm_lease_v1_manager_offer_output(void *manager, void *output) {
	(void)manager; (void)output; return false;
}
void wlr_drm_lease_request_v1_grant(void *request) { (void)request; }
void wlr_drm_lease_request_v1_reject(void *request) { (void)request; }

/* ---- 剩余 3 个 ---- */
bool wlr_backend_is_x11(void *backend) { (void)backend; return false; }
void wlr_drm_connector_add_mode(void *conn, const void *mode) { (void)conn; (void)mode; }
int wlr_drm_connector_get_panel_orientation(void *conn) { (void)conn; return 0; }
