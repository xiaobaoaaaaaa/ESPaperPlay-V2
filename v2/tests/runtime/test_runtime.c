#include "epp_runtime.h"

#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#define CHECK(expression)                                                                          \
    do {                                                                                           \
        if (!(expression)) {                                                                       \
            fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #expression);                         \
            return false;                                                                          \
        }                                                                                          \
    } while (0)

typedef struct {
    epp_app_host_t *host;
    unsigned enters;
    unsigned leaves;
    unsigned fail_on_enter;
    epp_app_token_t token;
    bool try_reentry;
    bool token_visible_during_enter;
    bool token_visible_during_leave;
    epp_status_t reentry_result;
} app_context_t;

static epp_status_t app_enter(void *context, epp_app_token_t token) {
    app_context_t *app = context;
    ++app->enters;
    app->token = token;
    app->token_visible_during_enter = epp_app_token_is_current(app->host, token);
    if (app->try_reentry) {
        app->reentry_result = epp_app_switch(app->host, token.app_id);
    }
    return app->enters == app->fail_on_enter ? EPP_ERR_FAILED : EPP_OK;
}

static void app_leave(void *context) {
    app_context_t *app = context;
    ++app->leaves;
    app->token_visible_during_leave = epp_app_token_is_current(app->host, app->token);
}

static epp_app_descriptor_t descriptor(uint32_t id, app_context_t *context) {
    return (epp_app_descriptor_t){
        .id = id, .name = "test-app", .context = context, .enter = app_enter, .leave = app_leave};
}

static bool test_app_validation_and_capacity(void) {
    epp_app_host_t host;
    epp_app_host_init(&host);
    app_context_t context = {.host = &host};
    epp_app_descriptor_t app = descriptor(1, &context);
    CHECK(epp_app_register(NULL, &app) == EPP_ERR_INVALID_ARG);
    CHECK(epp_app_register(&host, NULL) == EPP_ERR_INVALID_ARG);
    app.id = 0;
    CHECK(epp_app_register(&host, &app) == EPP_ERR_INVALID_ARG);
    app = descriptor(1, &context);
    app.enter = NULL;
    CHECK(epp_app_register(&host, &app) == EPP_ERR_INVALID_ARG);
    app = descriptor(1, &context);
    app.leave = NULL;
    CHECK(epp_app_register(&host, &app) == EPP_ERR_INVALID_ARG);
    app = descriptor(1, &context);
    app.name = "";
    CHECK(epp_app_register(&host, &app) == EPP_ERR_INVALID_ARG);
    for (uint32_t id = 1; id <= EPP_APP_CAPACITY; ++id) {
        app = descriptor(id, &context);
        CHECK(epp_app_register(&host, &app) == EPP_OK);
    }
    CHECK(epp_app_register(&host, &app) == EPP_ERR_EXISTS);
    app = descriptor(EPP_APP_CAPACITY + 1, &context);
    CHECK(epp_app_register(&host, &app) == EPP_ERR_CAPACITY);
    CHECK(epp_app_switch(&host, 1) == EPP_OK);
    const epp_app_token_t before = epp_app_current_token(&host);
    CHECK(epp_app_switch(&host, 100) == EPP_ERR_NOT_FOUND);
    CHECK(epp_app_switch(&host, 0) == EPP_ERR_INVALID_ARG);
    CHECK(context.leaves == 0);
    CHECK(epp_app_token_is_current(&host, before));
    CHECK(epp_app_close(&host) == EPP_OK);
    return true;
}

static bool test_app_switch_rejects_stale_results(void) {
    epp_app_host_t host;
    epp_app_host_init(&host);
    app_context_t a = {.host = &host};
    app_context_t b = {.host = &host};
    epp_app_descriptor_t app_a = descriptor(1, &a);
    epp_app_descriptor_t app_b = descriptor(2, &b);
    CHECK(epp_app_register(&host, &app_a) == EPP_OK);
    CHECK(epp_app_register(&host, &app_b) == EPP_OK);
    CHECK(!epp_app_token_is_current(&host, (epp_app_token_t){0}));
    CHECK(epp_app_switch(&host, 1) == EPP_OK);
    const epp_app_token_t pending_result = epp_app_current_token(&host);
    CHECK(epp_app_switch(&host, 1) == EPP_OK);
    CHECK(a.enters == 1 && a.leaves == 0);
    CHECK(epp_app_token_is_current(&host, pending_result));
    CHECK(epp_app_switch(&host, 2) == EPP_OK);
    CHECK(a.leaves == 1 && b.enters == 1);
    CHECK(!epp_app_token_is_current(&host, pending_result));
    CHECK(epp_app_switch(&host, 1) == EPP_OK);
    CHECK(!epp_app_token_is_current(&host, pending_result));
    CHECK(a.token.generation > pending_result.generation);
    CHECK(epp_app_token_is_current(&host, a.token));
    CHECK(!a.token_visible_during_enter && !a.token_visible_during_leave);
    CHECK(epp_app_close(&host) == EPP_OK);
    CHECK(!epp_app_token_is_current(&host, a.token));
    CHECK(epp_app_close(&host) == EPP_OK);
    CHECK(a.leaves == 2);
    return true;
}

static bool test_app_failed_entry_restores_with_fresh_token(void) {
    epp_app_host_t host;
    epp_app_host_init(&host);
    app_context_t a = {.host = &host};
    app_context_t b = {.host = &host, .fail_on_enter = 1};
    epp_app_descriptor_t app_a = descriptor(1, &a);
    epp_app_descriptor_t app_b = descriptor(2, &b);
    CHECK(epp_app_register(&host, &app_a) == EPP_OK);
    CHECK(epp_app_register(&host, &app_b) == EPP_OK);
    CHECK(epp_app_switch(&host, 1) == EPP_OK);
    const epp_app_token_t before = a.token;
    CHECK(epp_app_switch(&host, 2) == EPP_ERR_FAILED);
    CHECK(a.enters == 2 && a.leaves == 1);
    CHECK(b.enters == 1 && b.leaves == 1);
    CHECK(epp_app_token_is_current(&host, a.token));
    CHECK(!epp_app_token_is_current(&host, before));
    CHECK(!epp_app_token_is_current(&host, b.token));
    CHECK(epp_app_close(&host) == EPP_OK);
    return true;
}

static bool test_app_restore_failure_has_no_foreground(void) {
    epp_app_host_t host;
    epp_app_host_init(&host);
    app_context_t a = {.host = &host, .fail_on_enter = 2};
    app_context_t b = {.host = &host, .fail_on_enter = 1};
    epp_app_descriptor_t app_a = descriptor(1, &a);
    epp_app_descriptor_t app_b = descriptor(2, &b);
    CHECK(epp_app_register(&host, &app_a) == EPP_OK);
    CHECK(epp_app_register(&host, &app_b) == EPP_OK);
    CHECK(epp_app_switch(&host, 1) == EPP_OK);
    CHECK(epp_app_switch(&host, 2) == EPP_ERR_RESTORE_FAILED);
    CHECK(epp_app_current_token(&host).app_id == 0);
    CHECK(a.leaves == 2 && b.leaves == 1);
    CHECK(!epp_app_token_is_current(&host, a.token));
    CHECK(epp_app_switch(&host, 2) == EPP_OK);
    CHECK(epp_app_close(&host) == EPP_OK);
    return true;
}

static bool test_app_initial_entry_failure_cleans_up(void) {
    epp_app_host_t host;
    epp_app_host_init(&host);
    app_context_t context = {.host = &host, .fail_on_enter = 1};
    epp_app_descriptor_t app = descriptor(1, &context);
    CHECK(epp_app_register(&host, &app) == EPP_OK);
    CHECK(epp_app_switch(&host, 1) == EPP_ERR_FAILED);
    CHECK(context.enters == 1 && context.leaves == 1);
    CHECK(epp_app_current_token(&host).app_id == 0);
    CHECK(!epp_app_token_is_current(&host, context.token));
    return true;
}

static bool test_app_reentry_cross_host_and_exhaustion(void) {
    epp_app_host_t host;
    epp_app_host_t other;
    epp_app_host_init(&host);
    epp_app_host_init(&other);
    app_context_t a = {.host = &host, .try_reentry = true};
    app_context_t b = {.host = &other};
    epp_app_descriptor_t app_a = descriptor(1, &a);
    epp_app_descriptor_t app_b = descriptor(1, &b);
    CHECK(epp_app_register(&host, &app_a) == EPP_OK);
    CHECK(epp_app_register(&other, &app_b) == EPP_OK);
    CHECK(epp_app_switch(&host, 1) == EPP_OK);
    CHECK(epp_app_switch(&other, 1) == EPP_OK);
    CHECK(a.reentry_result == EPP_ERR_BUSY);
    CHECK(!epp_app_token_is_current(&host, b.token));
    app_a.id = 2;
    CHECK(epp_app_register(&host, &app_a) == EPP_OK);
    /* Deliberately inject near-overflow state to exercise the no-wrap guard. */
    host.last_generation = UINT64_MAX - 1;
    CHECK(epp_app_switch(&host, 2) == EPP_ERR_EXHAUSTED);
    CHECK(a.leaves == 0 && a.enters == 1);
    CHECK(epp_app_token_is_current(&host, a.token));
    CHECK(epp_app_close(&host) == EPP_OK);
    CHECK(epp_app_close(&other) == EPP_OK);
    host.last_generation = UINT64_MAX;
    CHECK(epp_app_switch(&host, 1) == EPP_ERR_EXHAUSTED);
    return true;
}

typedef struct {
    char text[128];
    size_t length;
} trace_t;

typedef struct {
    trace_t *trace;
    char id;
    bool fail;
    epp_sleep_depth_t prepared_depth;
    epp_sleep_depth_t resumed_depth;
    bool slept;
    epp_power_t *power;
    bool try_reentry;
    epp_status_t acquire_result;
    epp_status_t prepare_result;
    epp_status_t resume_result;
} participant_context_t;

static void trace_append(trace_t *trace, char operation, char id) {
    if (trace->length + 3 < sizeof(trace->text)) {
        trace->text[trace->length++] = operation;
        trace->text[trace->length++] = id;
        trace->text[trace->length++] = ' ';
        trace->text[trace->length] = '\0';
    }
}

static epp_status_t participant_prepare(void *context, epp_sleep_depth_t depth) {
    participant_context_t *participant = context;
    participant->prepared_depth = depth;
    trace_append(participant->trace, 'P', participant->id);
    if (participant->try_reentry) {
        epp_lease_t lease;
        participant->acquire_result = epp_power_acquire(participant->power, 10, EPP_SLEEP_ALL, &lease);
        participant->prepare_result = epp_power_prepare(participant->power, depth);
    }
    return participant->fail ? EPP_ERR_FAILED : EPP_OK;
}

static void participant_resume(void *context, epp_sleep_depth_t depth, bool slept) {
    participant_context_t *participant = context;
    participant->resumed_depth = depth;
    participant->slept = slept;
    trace_append(participant->trace, 'R', participant->id);
    if (participant->try_reentry) {
        participant->resume_result = epp_power_resume(participant->power, slept);
    }
}

static epp_sleep_participant_t sleep_descriptor(const char *name, participant_context_t *context) {
    return (epp_sleep_participant_t){
        .name = name, .context = context, .prepare = participant_prepare, .resume = participant_resume};
}

static bool test_leases_ownership_staleness_and_capacity(void) {
    epp_power_t power;
    epp_power_t other;
    epp_power_init(&power);
    epp_power_init(&other);
    epp_lease_t leases[EPP_LEASE_CAPACITY];
    CHECK(epp_power_acquire(NULL, 1, EPP_SLEEP_ALL, &leases[0]) == EPP_ERR_INVALID_ARG);
    CHECK(epp_power_acquire(&power, 0, EPP_SLEEP_ALL, &leases[0]) == EPP_ERR_INVALID_ARG);
    CHECK(epp_power_acquire(&power, 1, 0, &leases[0]) == EPP_ERR_INVALID_ARG);
    CHECK(epp_power_acquire(&power, 1, 4, &leases[0]) == EPP_ERR_INVALID_ARG);
    CHECK(epp_power_acquire(&power, 1, EPP_SLEEP_ALL, NULL) == EPP_ERR_INVALID_ARG);
    for (size_t i = 0; i < EPP_LEASE_CAPACITY; ++i) {
        CHECK(epp_power_acquire(&power, (uint32_t)i + 1, EPP_SLEEP_ALL, &leases[i]) == EPP_OK);
    }
    epp_lease_t overflow = {0};
    CHECK(epp_power_acquire(&power, 100, EPP_SLEEP_ALL, &overflow) == EPP_ERR_CAPACITY);
    CHECK(epp_power_blocker_count(&power, EPP_SLEEP_LIGHT) == EPP_LEASE_CAPACITY);
    CHECK(epp_power_release(&other, leases[0]) == EPP_ERR_STALE);
    epp_lease_t wrong_owner = leases[0];
    wrong_owner.owner_id = 100;
    CHECK(epp_power_release(&power, wrong_owner) == EPP_ERR_STALE);
    CHECK(epp_power_release(&power, (epp_lease_t){0}) == EPP_ERR_STALE);
    CHECK(epp_power_release(&power, leases[0]) == EPP_OK);
    CHECK(epp_power_release(&power, leases[0]) == EPP_ERR_STALE);
    const epp_lease_t expired = leases[0];
    CHECK(epp_power_acquire(&power, 1, EPP_SLEEP_ALL, &leases[0]) == EPP_OK);
    CHECK(leases[0].slot == expired.slot && leases[0].serial != expired.serial);
    CHECK(epp_power_release(&power, expired) == EPP_ERR_STALE);
    CHECK(epp_power_blocker_count(&power, EPP_SLEEP_LIGHT) == EPP_LEASE_CAPACITY);
    for (size_t i = 0; i < EPP_LEASE_CAPACITY; ++i) {
        CHECK(epp_power_release(&power, leases[i]) == EPP_OK);
    }
    CHECK(epp_power_blocker_count(&power, EPP_SLEEP_LIGHT) == 0);
    power.last_serial = UINT64_MAX;
    CHECK(epp_power_acquire(&power, 1, EPP_SLEEP_ALL, &overflow) == EPP_ERR_EXHAUSTED);
    return true;
}

static bool test_sleep_depth_constraints(void) {
    epp_power_t power;
    epp_power_init(&power);
    epp_lease_t deep_only;
    CHECK(epp_power_acquire(&power, 1, EPP_SLEEP_DEEP, &deep_only) == EPP_OK);
    CHECK(epp_power_blocker_count(&power, EPP_SLEEP_DEEP) == 1);
    CHECK(epp_power_blocker_count(&power, EPP_SLEEP_LIGHT) == 0);
    CHECK(epp_power_prepare(&power, EPP_SLEEP_DEEP) == EPP_ERR_BUSY);
    CHECK(!epp_power_is_prepared(&power));
    CHECK(epp_power_prepare(&power, EPP_SLEEP_LIGHT) == EPP_OK);
    CHECK(epp_power_is_prepared(&power));
    CHECK(epp_power_release(&power, deep_only) == EPP_ERR_BUSY);
    CHECK(epp_power_resume(&power, true) == EPP_OK);
    CHECK(epp_power_release(&power, deep_only) == EPP_OK);
    CHECK(epp_power_prepare(&power, EPP_SLEEP_DEEP) == EPP_OK);
    CHECK(epp_power_resume(&power, false) == EPP_OK);
    return true;
}

static bool test_sleep_order_wake_and_entry_cancellation(void) {
    epp_power_t power;
    epp_power_init(&power);
    trace_t trace = {0};
    participant_context_t a = {.trace = &trace, .id = 'A'};
    participant_context_t b = {.trace = &trace, .id = 'B'};
    epp_sleep_participant_t pa = sleep_descriptor("A", &a);
    epp_sleep_participant_t pb = sleep_descriptor("B", &b);
    CHECK(epp_power_register(&power, &pa) == EPP_OK);
    CHECK(epp_power_register(&power, &pb) == EPP_OK);
    epp_lease_t busy;
    CHECK(epp_power_acquire(&power, 1, EPP_SLEEP_ALL, &busy) == EPP_OK);
    CHECK(epp_power_prepare(&power, EPP_SLEEP_LIGHT) == EPP_ERR_BUSY);
    CHECK(trace.length == 0);
    CHECK(epp_power_release(&power, busy) == EPP_OK);
    CHECK(epp_power_prepare(&power, EPP_SLEEP_LIGHT) == EPP_OK);
    CHECK(strcmp(trace.text, "PA PB ") == 0);
    CHECK(epp_power_is_prepared(&power));
    CHECK(epp_power_prepare(&power, EPP_SLEEP_DEEP) == EPP_ERR_BUSY);
    CHECK(epp_power_acquire(&power, 1, EPP_SLEEP_ALL, &busy) == EPP_ERR_BUSY);
    CHECK(epp_power_register(&power, &pa) == EPP_ERR_BUSY);
    CHECK(epp_power_resume(&power, true) == EPP_OK);
    CHECK(strcmp(trace.text, "PA PB RB RA ") == 0);
    CHECK(a.slept && b.slept);
    CHECK(a.prepared_depth == EPP_SLEEP_LIGHT && a.resumed_depth == EPP_SLEEP_LIGHT);
    CHECK(!epp_power_is_prepared(&power));
    CHECK(epp_power_resume(&power, true) == EPP_ERR_STALE);
    trace = (trace_t){0};
    CHECK(epp_power_prepare(&power, EPP_SLEEP_DEEP) == EPP_OK);
    /* Simulate hardware sleep entry refusing after all preparation succeeded. */
    CHECK(epp_power_resume(&power, false) == EPP_OK);
    CHECK(strcmp(trace.text, "PA PB RB RA ") == 0);
    CHECK(!a.slept && !b.slept && a.resumed_depth == EPP_SLEEP_DEEP);
    return true;
}

static bool test_sleep_failed_prepare_rolls_back_including_failure(void) {
    epp_power_t power;
    epp_power_init(&power);
    trace_t trace = {0};
    participant_context_t a = {.trace = &trace, .id = 'A'};
    participant_context_t b = {.trace = &trace, .id = 'B', .fail = true};
    participant_context_t c = {.trace = &trace, .id = 'C'};
    epp_sleep_participant_t participants[] = {
        sleep_descriptor("A", &a), sleep_descriptor("B", &b), sleep_descriptor("C", &c)};
    for (size_t i = 0; i < 3; ++i) {
        CHECK(epp_power_register(&power, &participants[i]) == EPP_OK);
    }
    CHECK(epp_power_prepare(&power, EPP_SLEEP_DEEP) == EPP_ERR_FAILED);
    CHECK(strcmp(trace.text, "PA PB RB RA ") == 0);
    CHECK(!a.slept && !b.slept);
    CHECK(c.prepared_depth == 0 && c.resumed_depth == 0);
    CHECK(!epp_power_is_prepared(&power));
    epp_lease_t lease;
    CHECK(epp_power_acquire(&power, 1, EPP_SLEEP_ALL, &lease) == EPP_OK);
    CHECK(epp_power_release(&power, lease) == EPP_OK);
    b.fail = false;
    trace = (trace_t){0};
    CHECK(epp_power_prepare(&power, EPP_SLEEP_DEEP) == EPP_OK);
    CHECK(epp_power_resume(&power, true) == EPP_OK);
    CHECK(strcmp(trace.text, "PA PB PC RC RB RA ") == 0);
    return true;
}

static bool test_sleep_registration_validation_capacity_and_reentry(void) {
    epp_power_t power;
    epp_power_init(&power);
    trace_t trace = {0};
    participant_context_t context = {.trace = &trace, .id = 'A', .power = &power, .try_reentry = true};
    epp_sleep_participant_t participant = sleep_descriptor("A", &context);
    CHECK(epp_power_register(NULL, &participant) == EPP_ERR_INVALID_ARG);
    CHECK(epp_power_register(&power, NULL) == EPP_ERR_INVALID_ARG);
    participant.prepare = NULL;
    CHECK(epp_power_register(&power, &participant) == EPP_ERR_INVALID_ARG);
    participant = sleep_descriptor("", &context);
    CHECK(epp_power_register(&power, &participant) == EPP_ERR_INVALID_ARG);
    const char *names[] = {"A", "B", "C", "D", "E", "F", "G", "H"};
    CHECK(sizeof(names) / sizeof(names[0]) == EPP_SLEEP_PARTICIPANT_CAPACITY);
    for (size_t i = 0; i < EPP_SLEEP_PARTICIPANT_CAPACITY; ++i) {
        participant = sleep_descriptor(names[i], &context);
        CHECK(epp_power_register(&power, &participant) == EPP_OK);
    }
    CHECK(epp_power_register(&power, &participant) == EPP_ERR_EXISTS);
    participant = sleep_descriptor("extra", &context);
    CHECK(epp_power_register(&power, &participant) == EPP_ERR_CAPACITY);
    CHECK(epp_power_prepare(&power, (epp_sleep_depth_t)0) == EPP_ERR_INVALID_ARG);
    CHECK(epp_power_prepare(&power, (epp_sleep_depth_t)EPP_SLEEP_ALL) == EPP_ERR_INVALID_ARG);
    CHECK(epp_power_prepare(&power, EPP_SLEEP_LIGHT) == EPP_OK);
    CHECK(context.acquire_result == EPP_ERR_BUSY);
    CHECK(context.prepare_result == EPP_ERR_BUSY);
    CHECK(epp_power_resume(&power, false) == EPP_OK);
    CHECK(context.resume_result == EPP_ERR_BUSY);
    return true;
}

int main(void) {
    const struct {
        const char *name;
        bool (*run)(void);
    } tests[] = {
        {"app validation and registry capacity", test_app_validation_and_capacity},
        {"app switching rejects stale results", test_app_switch_rejects_stale_results},
        {"failed entry restores with fresh token", test_app_failed_entry_restores_with_fresh_token},
        {"failed restoration leaves no foreground", test_app_restore_failure_has_no_foreground},
        {"failed first entry cleans partial state", test_app_initial_entry_failure_cleans_up},
        {"app reentry, cross-host tokens and generation exhaustion", test_app_reentry_cross_host_and_exhaustion},
        {"lease ownership, staleness and capacity", test_leases_ownership_staleness_and_capacity},
        {"light/deep sleep constraints", test_sleep_depth_constraints},
        {"sleep wake ordering and hardware-entry cancellation", test_sleep_order_wake_and_entry_cancellation},
        {"failed prepare rolls back partial participant", test_sleep_failed_prepare_rolls_back_including_failure},
        {"sleep registration, capacity and reentry", test_sleep_registration_validation_capacity_and_reentry},
    };
    for (size_t i = 0; i < sizeof(tests) / sizeof(tests[0]); ++i) {
        if (!tests[i].run()) {
            fprintf(stderr, "FAIL: %s\n", tests[i].name);
            return 1;
        }
        printf("PASS: %s\n", tests[i].name);
    }
    printf("All %zu runtime scenarios passed.\n", sizeof(tests) / sizeof(tests[0]));
    return 0;
}
