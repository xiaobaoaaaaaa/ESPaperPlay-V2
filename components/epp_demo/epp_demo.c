#include "epp_demo.h"

typedef struct {
    const char *name;
    epp_demo_log_fn log;
    void *log_context;
    bool entered;
} demo_app_t;

static epp_status_t enter(void *context, epp_app_token_t token) {
    demo_app_t *app = context;
    (void)token;
    app->entered = true;
    app->log(app->log_context, app->name);
    return EPP_OK;
}

static void leave(void *context) {
    demo_app_t *app = context;
    app->entered = false;
}

static epp_status_t prepare(void *context, epp_sleep_depth_t depth) {
    bool *prepared = context;
    (void)depth;
    *prepared = true;
    return EPP_OK;
}

static void resume(void *context, epp_sleep_depth_t depth, bool slept) {
    bool *prepared = context;
    (void)depth;
    (void)slept;
    *prepared = false;
}

#define REQUIRE(condition) do { if (!(condition)) return EPP_ERR_FAILED; } while (0)

epp_status_t epp_demo_run(epp_demo_log_fn log, void *context) {
    if (log == NULL) return EPP_ERR_INVALID_ARG;
    epp_app_host_t host;
    epp_power_t power;
    epp_app_host_init(&host);
    epp_power_init(&power);
    demo_app_t reader = {.name = "foreground: reader placeholder", .log = log, .log_context = context};
    demo_app_t player = {.name = "foreground: player placeholder", .log = log, .log_context = context};
    const epp_app_descriptor_t apps[] = {
        {.id = 1, .name = "reader", .context = &reader, .enter = enter, .leave = leave},
        {.id = 2, .name = "player", .context = &player, .enter = enter, .leave = leave},
    };
    REQUIRE(epp_app_register(&host, &apps[0]) == EPP_OK);
    REQUIRE(epp_app_register(&host, &apps[1]) == EPP_OK);
    REQUIRE(epp_app_switch(&host, 1) == EPP_OK);
    const epp_app_token_t old_view = epp_app_current_token(&host);
    epp_lease_t background_session;
    REQUIRE(epp_power_acquire(&power, 100, EPP_SLEEP_ALL, &background_session) == EPP_OK);
    REQUIRE(epp_app_switch(&host, 2) == EPP_OK);
    REQUIRE(!reader.entered && player.entered);
    REQUIRE(!epp_app_token_is_current(&host, old_view));
    REQUIRE(epp_app_token_is_current(&host, epp_app_current_token(&host)));
    REQUIRE(epp_power_blocker_count(&power, EPP_SLEEP_LIGHT) == 1);
    REQUIRE(epp_power_prepare(&power, EPP_SLEEP_LIGHT) == EPP_ERR_BUSY);
    log(context, "background session survived app switch; stale view rejected; sleep blocked");
    REQUIRE(epp_power_release(&power, background_session) == EPP_OK);
    bool prepared = false;
    const epp_sleep_participant_t participant = {
        .name = "simulated-service", .context = &prepared, .prepare = prepare, .resume = resume};
    REQUIRE(epp_power_register(&power, &participant) == EPP_OK);
    REQUIRE(epp_power_prepare(&power, EPP_SLEEP_LIGHT) == EPP_OK && prepared);
    /* Cancel the prepared transition: this demo never enters hardware sleep. */
    REQUIRE(epp_power_resume(&power, false) == EPP_OK && !prepared);
    REQUIRE(epp_app_close(&host) == EPP_OK && !player.entered);
    log(context, "bootstrap scenario passed (simulated services; no hardware I/O)");
    return EPP_OK;
}
