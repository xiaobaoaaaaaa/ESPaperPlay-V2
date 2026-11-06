#pragma once

#include "epp_runtime.h"

/* Console-only integration scenario. No display, audio, network or sleep I/O. */
typedef void (*epp_demo_log_fn)(void *context, const char *message);
epp_status_t epp_demo_run(epp_demo_log_fn log, void *context);
