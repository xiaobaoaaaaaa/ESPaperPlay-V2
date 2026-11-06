# ESPaperPlay v2 开发工程

这是多功能电子纸平台的独立重构工程。主控固定为 **ESP32-S3-WROOM-1-N16R8（16 MB Flash / 8 MB PSRAM）**，复用现有 7.5 英寸屏幕。固件、硬件和设计文档现由独立的 ESPaperPlay-V2 仓库管理；[旧版工程](https://github.com/xiaobaoaaaaaa/ESPaperPlay/tree/0f6d7c349afdbbeb962a736d84036ce7f8487174)保留在原仓库作为迁移参考，本工程不链接旧版组件。

设计入口：[项目设计与进度](../docs/v2/README.md)。

## 当前实现

- 无动态分配的 C11 应用宿主：静态注册、切换失败恢复、前台实例代号与旧结果拒绝。
- 有界活动租约：区分浅睡／深睡约束，拒绝重复或过期释放。
- 休眠准备与逆序恢复：包括准备失败和硬件入睡取消的清理契约。
- 主机运行与固件共用的串口演示：切换两个占位应用，模拟后台会话持续，验证休眠约束。
- 现有板级元数据校验：GPIO 可用性、冲突、绑带注解、USB 和存储容量约束。
- 16 MiB 双槽 OTA 分区原型及启动健康检查。
- 主机测试、ASan/UBSan 与独立固件 CI。

这是 **M0 串口骨架**：不初始化外设 GPIO，不显示实际页面，不播放音频，不联网，不执行芯片休眠。实例代号校验尚不包含工作队列和任务取消。双槽与启动确认不等于已经提供 OTA 下载客户端。后续计划见 [roadmap.md](../docs/v2/roadmap.md)。

## 主机验证

以下命令均从仓库根目录执行，无需 ESP-IDF：

```sh
cmake -S v2/tests -B v2/build/host -G Ninja \
  -DCMAKE_C_COMPILER=clang -DCMAKE_BUILD_TYPE=Debug
cmake --build v2/build/host
ctest --test-dir v2/build/host --output-on-failure
./v2/build/host/bootstrap_demo
```

需要 CMake 3.22+、Clang 或 GCC、Ninja 和 Python 3。默认启用 ASan/UBSan；在不支持 sanitizer 的主机上可显式传入 `-DEPP_SANITIZERS=OFF`，但需在其他环境补做 sanitizer 检查。

## ESP32-S3 构建

先激活 **ESP-IDF 6.1**。通过 Espressif Installation Manager 安装的环境，使用安装器生成的激活脚本；普通安装使用 `$IDF_PATH/export.sh`。工具链路径不写入工程。

```sh
idf.py --version
idf.py -C v2 -B build/esp32s3 build
```

产物在仓库根目录的 `build/esp32s3/`，与主机测试目录分开。当前没有第三方 managed component 依赖；接入 LVGL 等库时再锁定对应版本。`sdkconfig.defaults` 配置 N16R8、Octal PSRAM、USB Serial/JTAG 日志及新分区表。

固件启动时核对实际 Flash/PSRAM 容量，执行串口集成场景；若当前镜像为 OTA 待验证状态，只有通过这些 M0 健康检查才确认镜像。它尚不检查显示、SD、音频或网络的健康。

## 板级与分区边界

`boards/legacy_n16r8.json` 来自旧版提交 `0f6d7c349afdbbeb962a736d84036ce7f8487174` 的配置，并非新主板的最终 GPIO 表。旧板 SD 默认 1-bit，屏幕／触摸／SD 共轨；新板设计另见 [硬件文档](../docs/v2/hardware/README.md)。固件目前只消费生成的身份和容量元数据，不操作其中的引脚。

新分区原型：两个 5 MiB 应用槽、4 MiB 基础资源区、剩余状态区与系统元数据。资源区和状态区尚未挂载或写入。这一分区与旧版 4 MiB factory + 8 MiB fonts 布局不兼容，首次迁移必须单独安排备份和完整烧录；不能把本开发镜像作为旧版本的普通应用更新。

本轮只构建，不自动连接设备、擦除、烧录或下单制板。
