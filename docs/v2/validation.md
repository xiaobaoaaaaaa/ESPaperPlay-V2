# M0 本地验证记录

> 本页保留迁移前2026-11-01的检查记录、环境与分支名，不代表独立仓库迁移后的重新验证。

日期：2026-11-01（Asia/Shanghai）。工作分支：`refactor/v2-platform`。旧版基点：`0f6d7c349afdbbeb962a736d84036ce7f8487174`。

## 环境与范围

- 主机：Linux，Clang 22.1.8，Python 3.14.8，CMake/Ninja。
- 固件：ESP-IDF v6.1，ESP32-S3，16 MiB Flash / 8 MiB Octal PSRAM 配置。
- 本机 SDK 由 Espressif Installation Manager 安装，使用其生成的激活脚本；工程不依赖该机器的绝对安装路径。
- 本记录对应串口骨架；未进行实机启动、烧录、OTA 切换、功耗或面板测试。

## 已执行检查

| 检查 | 结果 | 覆盖范围 |
| --- | --- | --- |
| C11 主机严格编译 | 通过 | `-Wall -Wextra -Wpedantic -Werror` |
| CTest | **5/5 通过** | 运行时、串口集成场景、板级配置、分区、无效配置拒绝 |
| 运行时场景 | **11/11 通过** | 应用切换与失败恢复、旧代号、容量、句柄、休眠约束和逆序回滚 |
| Python 配置负例 | **13/13 通过** | 内存占用脚、GPIO 冲突、USB、绑带、GPIO46、SD 必需信号、分区重叠/越界等 |
| AddressSanitizer / UndefinedBehaviorSanitizer | 通过 | 当前主机 C 测试与集成场景，没有报告内存错误或未定义行为 |
| ESP-IDF 固件交叉编译 | 通过 | 新工程独立构建，生成 app/bootloader/partition/OTA 初始化数据 |
| 分区容量检查 | 通过 | 两个 5 MiB 槽，整体位于 16 MiB Flash 范围内 |
| CI 工作流 YAML | 本地解析通过 | 新增主机和固件构建任务；尚未推送运行远端 CI |

复现命令（仓库根目录）：

```sh
cmake -S v2/tests -B v2/build/host -G Ninja \
  -DCMAKE_C_COMPILER=clang -DCMAKE_BUILD_TYPE=Debug
cmake --build v2/build/host
ctest --test-dir v2/build/host --output-on-failure
./v2/build/host/runtime_tests
python3 v2/tests/test_config.py

# 激活 ESP-IDF 6.1 后
idf.py -C v2 -B build/esp32s3 build
```

当前应用镜像：`build/esp32s3/ESPaperPlay_v2.bin`，**177,344 bytes（0x2b4c0）**。这是未包含 LVGL、字体和真实业务服务的骨架大小，不能用于推断完整平台的最终容量。

## 审阅后修正

1. 待确认 OTA 镜像在内存或运行时健康检查失败时，立即请求回滚；如果没有可用旧镜像，则保留 USB 诊断并记录错误。实际回滚行为仍需双镜像上板测试。
2. 板级校验要求所有 SD 模式均具有 CLK/CMD/D0，4-bit 模式另要求 D1–D3；缺失信号负例已覆盖。
3. 硬件路线明确先制作开发验证板，验证通过后再收敛产品尺寸。

## 仍未验证或实现

- 新板原理图/ERC、PCB/DRC、最终器件和 FPC 接口核对。
- 实际 Flash/PSRAM 上电稳定性与 USB 串口启动日志。
- 真实页面、驱动迁移、音频、网络、SD 文件服务与后台任务取消。
- 真实睡眠、唤醒、独立电源域与掉电隔离。
- OTA 下载、旧分区迁移、断电升级与完整系统健康检查。
- 全部功耗、峰值电流、温升与续航验收。

代码和硬件设计草案保存在本地工作分支，尚未提交或推送；没有连接设备、擦除、烧录、采购或制造操作。
