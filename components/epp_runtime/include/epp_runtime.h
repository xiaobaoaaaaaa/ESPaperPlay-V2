#ifndef EPP_RUNTIME_H
#define EPP_RUNTIME_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* All calls, including callbacks, run on one owner thread. This library does not
 * provide locking. Initialize each object once, keep it at a stable address,
 * and do not copy it while in use. Descriptor strings/context outlive the object.
 * Callbacks may query state but must not mutate their own host/coordinator.
 * Fields are public for static allocation only; callers must not modify them.
 */
#define EPP_APP_CAPACITY 8u
#define EPP_LEASE_CAPACITY 16u
#define EPP_SLEEP_PARTICIPANT_CAPACITY 8u

typedef enum {
    EPP_OK = 0,
    EPP_ERR_INVALID_ARG = -1,
    EPP_ERR_NOT_FOUND = -2,
    EPP_ERR_CAPACITY = -3,
    EPP_ERR_BUSY = -4,
    EPP_ERR_FAILED = -5,
    EPP_ERR_RESTORE_FAILED = -6,
    EPP_ERR_STALE = -7,
    EPP_ERR_EXHAUSTED = -8,
    EPP_ERR_EXISTS = -9
} epp_status_t;

typedef struct epp_app_host epp_app_host_t;

typedef struct {
    const epp_app_host_t *host;
    uint32_t app_id;
    uint64_t generation;
} epp_app_token_t;

typedef struct {
    uint32_t id; /* Zero is reserved for no foreground app. */
    const char *name;
    void *context;
    epp_status_t (*enter)(void *context, epp_app_token_t token);
    /* Called for successful entries AND failed entry attempts. Must release
     * partial resources as well. Persistent background jobs belong to services,
     * not this foreground token. */
    void (*leave)(void *context);
} epp_app_descriptor_t;

struct epp_app_host {
    epp_app_descriptor_t apps[EPP_APP_CAPACITY];
    size_t app_count;
    size_t active_index;
    uint64_t last_generation;
    epp_app_token_t current;
    bool transitioning;
};

void epp_app_host_init(epp_app_host_t *host);
epp_status_t epp_app_register(epp_app_host_t *host, const epp_app_descriptor_t *app);
/* Unknown IDs never leave the current app. Switching to the current ID is a
 * no-op. On entry failure, clean the target and re-enter the previous app with
 * a NEW token; return the original failure if restoration succeeds. If restoring
 * also fails, clean both entries, leave no foreground app and return
 * EPP_ERR_RESTORE_FAILED. Token generations never wrap. */
epp_status_t epp_app_switch(epp_app_host_t *host, uint32_t app_id);
epp_status_t epp_app_close(epp_app_host_t *host);
epp_app_token_t epp_app_current_token(const epp_app_host_t *host);
/* Consumers must check this before applying asynchronous results to a view. */
bool epp_app_token_is_current(const epp_app_host_t *host, epp_app_token_t token);

typedef enum {
    EPP_SLEEP_LIGHT = 1u,
    EPP_SLEEP_DEEP = 2u
} epp_sleep_depth_t;

#define EPP_SLEEP_ALL ((uint32_t)EPP_SLEEP_LIGHT | (uint32_t)EPP_SLEEP_DEEP)

typedef struct epp_power epp_power_t;

typedef struct {
    const epp_power_t *coordinator;
    uint32_t owner_id;
    size_t slot;
    uint64_t serial;
} epp_lease_t;

typedef struct {
    const char *name;
    void *context;
    epp_status_t (*prepare)(void *context, epp_sleep_depth_t depth);
    /* Reverse-order restore on both wake and cancellation. The participant whose
     * prepare failed is also resumed (it may have partially prepared). Must be
     * safe after partial preparation; slept=false means no sleep was entered. */
    void (*resume)(void *context, epp_sleep_depth_t depth, bool slept);
} epp_sleep_participant_t;

typedef struct {
    uint32_t owner_id;
    uint32_t blocked_depths;
    uint64_t serial;
    bool active;
} epp_lease_slot_t;

struct epp_power {
    epp_lease_slot_t leases[EPP_LEASE_CAPACITY];
    uint64_t last_serial;
    epp_sleep_participant_t participants[EPP_SLEEP_PARTICIPANT_CAPACITY];
    size_t participant_count;
    size_t prepared_count;
    epp_sleep_depth_t prepared_depth;
    bool transitioning;
    bool prepared;
};

void epp_power_init(epp_power_t *power);
/* Nonzero owner IDs identify service sessions. blocked_depths is a nonempty
 * subset of EPP_SLEEP_ALL. Leases are explicit, do not expire, and must be
 * released by the owning service. Acquisition fails while preparing/prepared. */
epp_status_t epp_power_acquire(epp_power_t *power, uint32_t owner_id,
                             uint32_t blocked_depths, epp_lease_t *out_lease);
epp_status_t epp_power_release(epp_power_t *power, epp_lease_t lease);
size_t epp_power_blocker_count(const epp_power_t *power, epp_sleep_depth_t depth);
epp_status_t epp_power_register(epp_power_t *power,
                              const epp_sleep_participant_t *participant);
/* This coordinates preparation only; it never enters hardware sleep or switches
 * a power rail. The caller enters sleep after success, then calls resume. If
 * hardware entry fails, call resume(power, false) to cancel preparation. */
epp_status_t epp_power_prepare(epp_power_t *power, epp_sleep_depth_t depth);
epp_status_t epp_power_resume(epp_power_t *power, bool slept);
bool epp_power_is_prepared(const epp_power_t *power);

#ifdef __cplusplus
}
#endif

#endif
