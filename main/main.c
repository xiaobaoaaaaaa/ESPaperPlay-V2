#include <inttypes.h>

#include "epp_board_config.h"
#include "epp_demo.h"
#include "esp_flash.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_ota_ops.h"
#include "esp_psram.h"

static const char *TAG = "epp_bootstrap";

static void log_demo(void *context, const char *message) {
    (void)context;
    ESP_LOGI(TAG, "%s", message);
}

static void health_check_failed(bool pending_verification, const char *reason) {
    ESP_LOGE(TAG, "%s", reason);
    if (pending_verification) {
        const esp_err_t err = esp_ota_mark_app_invalid_rollback_and_reboot();
        /* Success restarts the device. No usable previous image is possible on
         * a development board, so preserve USB diagnostics if rollback fails. */
        ESP_LOGE(TAG, "Rollback could not restart the device: %s", esp_err_to_name(err));
    }
}

void app_main(void) {
    uint32_t flash_bytes = 0;
    const esp_partition_t *running = esp_ota_get_running_partition();
    esp_ota_img_states_t state;
    const bool pending_verification = running != NULL &&
        esp_ota_get_state_partition(running, &state) == ESP_OK && state == ESP_OTA_IMG_PENDING_VERIFY;
    ESP_LOGI(TAG, "profile=%s module=%s", EPP_BOARD_ID, EPP_BOARD_MODULE);
    if (esp_flash_get_size(NULL, &flash_bytes) != ESP_OK ||
        flash_bytes != EPP_BOARD_FLASH_BYTES || esp_psram_get_size() != EPP_BOARD_PSRAM_BYTES) {
        health_check_failed(pending_verification, "Board memory mismatch; expected 16 MiB Flash / 8 MiB PSRAM");
        return;
    }
    ESP_LOGI(TAG, "flash=%" PRIu32 " PSRAM=%zu internal-free=%zu", flash_bytes,
             esp_psram_get_size(), heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
    if (epp_demo_run(log_demo, NULL) != EPP_OK) {
        health_check_failed(pending_verification, "Bootstrap runtime health check failed");
        return;
    }
    if (pending_verification) {
        ESP_ERROR_CHECK(esp_ota_mark_app_valid_cancel_rollback());
    }
    ESP_LOGI(TAG, "Bootstrap ready. Peripheral GPIOs, display, audio, network and hardware sleep are not initialized.");
}
