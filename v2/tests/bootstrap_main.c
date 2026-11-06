#include <stdio.h>
#include "epp_demo.h"

static void log_line(void *context, const char *message) {
    (void)context;
    puts(message);
}

int main(void) {
    return epp_demo_run(log_line, NULL) == EPP_OK ? 0 : 1;
}
