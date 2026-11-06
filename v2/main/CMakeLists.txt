set(board_file "${PROJECT_DIR}/boards/legacy_n16r8.json")
set(board_tool "${PROJECT_DIR}/tools/check_board.py")
set(generated_dir "${CMAKE_CURRENT_BINARY_DIR}/generated")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${board_file}" "${board_tool}")
execute_process(
    COMMAND "${PYTHON}" "${board_tool}" "${board_file}" --header "${generated_dir}/epp_board_config.h"
    RESULT_VARIABLE board_result
)
if(NOT board_result EQUAL 0)
    message(FATAL_ERROR "Board profile validation failed")
endif()
idf_component_register(SRCS "main.c" INCLUDE_DIRS "${generated_dir}"
                      PRIV_REQUIRES epp_demo esp_psram spi_flash app_update esp_system)
