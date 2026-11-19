#include "epp_runtime.h"

#include <string.h>

static bool valid_depth(epp_sleep_depth_t depth) {
    return depth == EPP_SLEEP_LIGHT || depth == EPP_SLEEP_DEEP;
}

void epp_app_host_init(epp_app_host_t *host) {
    if (host != NULL) {
        memset(host, 0, sizeof(*host));
        host->active_index = EPP_APP_CAPACITY;
    }
}

epp_status_t epp_app_register(epp_app_host_t *host, const epp_app_descriptor_t *app) {
    if (host == NULL || app == NULL || app->id == 0 || app->name == NULL ||
        app->name[0] == '\0' || app->enter == NULL || app->leave == NULL) {
        return EPP_ERR_INVALID_ARG;
    }
    if (host->transitioning) {
        return EPP_ERR_BUSY;
    }
    for (size_t i = 0; i < host->app_count; ++i) {
        if (host->apps[i].id == app->id) {
            return EPP_ERR_EXISTS;
        }
    }
    if (host->app_count == EPP_APP_CAPACITY) {
        return EPP_ERR_CAPACITY;
    }
    host->apps[host->app_count++] = *app;
    return EPP_OK;
}

static epp_status_t enter_app(epp_app_host_t *host, size_t index) {
    const epp_app_descriptor_t *app = &host->apps[index];
    const epp_app_token_t token = {
        .host = host, .app_id = app->id, .generation = ++host->last_generation};
    const epp_status_t result = app->enter(app->context, token);
    if (result == EPP_OK) {
        host->active_index = index;
        host->current = token;
    } else {
        app->leave(app->context);
    }
    return result;
}

static void leave_current(epp_app_host_t *host) {
    const size_t previous = host->active_index;
    /* Invalidate the old token before invoking cleanup. */
    host->active_index = EPP_APP_CAPACITY;
    host->current = (epp_app_token_t){0};
    if (previous < host->app_count) {
        const epp_app_descriptor_t *app = &host->apps[previous];
        app->leave(app->context);
    }
}

epp_status_t epp_app_switch(epp_app_host_t *host, uint32_t app_id) {
    if (host == NULL || app_id == 0) {
        return EPP_ERR_INVALID_ARG;
    }
    if (host->transitioning) {
        return EPP_ERR_BUSY;
    }
    size_t target = EPP_APP_CAPACITY;
    for (size_t i = 0; i < host->app_count; ++i) {
        if (host->apps[i].id == app_id) {
            target = i;
            break;
        }
    }
    if (target == EPP_APP_CAPACITY) {
        return EPP_ERR_NOT_FOUND;
    }
    const size_t previous = host->active_index;
    if (target == previous) {
        return EPP_OK;
    }
    /* Reserve a second generation for restoration before leaving any view. */
    const uint64_t required = previous < host->app_count ? 2u : 1u;
    if (host->last_generation > UINT64_MAX - required) {
        return EPP_ERR_EXHAUSTED;
    }
    host->transitioning = true;
    leave_current(host);
    epp_status_t result = enter_app(host, target);
    if (result != EPP_OK && previous < host->app_count) {
        if (enter_app(host, previous) != EPP_OK) {
            result = EPP_ERR_RESTORE_FAILED;
        }
    }
    host->transitioning = false;
    return result;
}

epp_status_t epp_app_close(epp_app_host_t *host) {
    if (host == NULL) {
        return EPP_ERR_INVALID_ARG;
    }
    if (host->transitioning) {
        return EPP_ERR_BUSY;
    }
    host->transitioning = true;
    leave_current(host);
    host->transitioning = false;
    return EPP_OK;
}

epp_app_token_t epp_app_current_token(const epp_app_host_t *host) {
    return host != NULL ? host->current : (epp_app_token_t){0};
}

bool epp_app_token_is_current(const epp_app_host_t *host, epp_app_token_t token) {
    return host != NULL && !host->transitioning && token.host == host &&
           token.app_id != 0 && token.generation != 0 &&
           token.app_id == host->current.app_id && token.generation == host->current.generation;
}

void epp_power_init(epp_power_t *power) {
    if (power != NULL) {
        memset(power, 0, sizeof(*power));
    }
}

epp_status_t epp_power_acquire(epp_power_t *power, uint32_t owner_id,
                             uint32_t blocked_depths, epp_lease_t *out_lease) {
    if (power == NULL || out_lease == NULL || owner_id == 0 || blocked_depths == 0 ||
        (blocked_depths & ~EPP_SLEEP_ALL) != 0) {
        return EPP_ERR_INVALID_ARG;
    }
    if (power->transitioning || power->prepared) {
        return EPP_ERR_BUSY;
    }
    if (power->last_serial == UINT64_MAX) {
        return EPP_ERR_EXHAUSTED;
    }
    for (size_t i = 0; i < EPP_LEASE_CAPACITY; ++i) {
        if (!power->leases[i].active) {
            const uint64_t serial = ++power->last_serial;
            power->leases[i] = (epp_lease_slot_t){
                .owner_id = owner_id, .blocked_depths = blocked_depths,
                .serial = serial, .active = true};
            *out_lease = (epp_lease_t){
                .coordinator = power, .owner_id = owner_id, .slot = i, .serial = serial};
            return EPP_OK;
        }
    }
    return EPP_ERR_CAPACITY;
}

epp_status_t epp_power_release(epp_power_t *power, epp_lease_t lease) {
    if (power == NULL) {
        return EPP_ERR_INVALID_ARG;
    }
    if (power->transitioning || power->prepared) {
        return EPP_ERR_BUSY;
    }
    if (lease.coordinator != power || lease.slot >= EPP_LEASE_CAPACITY ||
        lease.owner_id == 0 || lease.serial == 0) {
        return EPP_ERR_STALE;
    }
    epp_lease_slot_t *slot = &power->leases[lease.slot];
    if (!slot->active || slot->serial != lease.serial || slot->owner_id != lease.owner_id) {
        return EPP_ERR_STALE;
    }
    *slot = (epp_lease_slot_t){0};
    return EPP_OK;
}

size_t epp_power_blocker_count(const epp_power_t *power, epp_sleep_depth_t depth) {
    if (power == NULL || !valid_depth(depth)) {
        return 0;
    }
    size_t count = 0;
    for (size_t i = 0; i < EPP_LEASE_CAPACITY; ++i) {
        if (power->leases[i].active && (power->leases[i].blocked_depths & (uint32_t)depth) != 0) {
            ++count;
        }
    }
    return count;
}

epp_status_t epp_power_register(epp_power_t *power,
                              const epp_sleep_participant_t *participant) {
    if (power == NULL || participant == NULL || participant->name == NULL ||
        participant->name[0] == '\0' || participant->prepare == NULL || participant->resume == NULL) {
        return EPP_ERR_INVALID_ARG;
    }
    if (power->transitioning || power->prepared) {
        return EPP_ERR_BUSY;
    }
    for (size_t i = 0; i < power->participant_count; ++i) {
        if (strcmp(power->participants[i].name, participant->name) == 0) {
            return EPP_ERR_EXISTS;
        }
    }
    if (power->participant_count == EPP_SLEEP_PARTICIPANT_CAPACITY) {
        return EPP_ERR_CAPACITY;
    }
    power->participants[power->participant_count++] = *participant;
    return EPP_OK;
}

static void resume_prepared(epp_power_t *power, bool slept) {
    while (power->prepared_count > 0) {
        const epp_sleep_participant_t *participant = &power->participants[--power->prepared_count];
        participant->resume(participant->context, power->prepared_depth, slept);
    }
}

epp_status_t epp_power_prepare(epp_power_t *power, epp_sleep_depth_t depth) {
    if (power == NULL || !valid_depth(depth)) {
        return EPP_ERR_INVALID_ARG;
    }
    if (power->transitioning || power->prepared || epp_power_blocker_count(power, depth) != 0) {
        return EPP_ERR_BUSY;
    }
    power->transitioning = true;
    power->prepared_depth = depth;
    for (size_t i = 0; i < power->participant_count; ++i) {
        const epp_sleep_participant_t *participant = &power->participants[i];
        /* Include the currently attempted participant in cancellation cleanup. */
        power->prepared_count = i + 1u;
        const epp_status_t result = participant->prepare(participant->context, depth);
        if (result != EPP_OK) {
            resume_prepared(power, false);
            power->prepared_depth = (epp_sleep_depth_t)0;
            power->transitioning = false;
            return result;
        }
    }
    power->prepared = true;
    power->transitioning = false;
    return EPP_OK;
}

epp_status_t epp_power_resume(epp_power_t *power, bool slept) {
    if (power == NULL) {
        return EPP_ERR_INVALID_ARG;
    }
    if (power->transitioning) {
        return EPP_ERR_BUSY;
    }
    if (!power->prepared) {
        return EPP_ERR_STALE;
    }
    power->transitioning = true;
    resume_prepared(power, slept);
    power->prepared = false;
    power->prepared_depth = (epp_sleep_depth_t)0;
    power->transitioning = false;
    return EPP_OK;
}

bool epp_power_is_prepared(const epp_power_t *power) {
    return power != NULL && power->prepared;
}
