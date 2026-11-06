# KiCad 本机环境

检查日期：2026-11-01。主机：Fedora 44 KDE、x86_64。

## 安装与库配置

通过 Fedora `fedora` / `updates` 仓库安装原生 RPM，没有使用 AppImage。

```sh
pkexec /usr/bin/dnf --assumeyes --repo=fedora --repo=updates install kicad kicad-packages3d kicad-doc
```

本次安装事务成功结束，实际版本：

| RPM | 版本 |
| --- | --- |
| kicad | 10.0.7-1.fc44.x86_64 |
| kicad-packages3d | 10.0.7-1.fc44.noarch |
| kicad-doc | 10.0.7-1.fc44.noarch |

`kicad-cli version` 返回 `10.0.7`。符号、封装、3D 模型和模板分别位于 `/usr/share/kicad/symbols`、`/usr/share/kicad/footprints`、`/usr/share/kicad/3dmodels` 和 `/usr/share/kicad/template`。

首次配置时，将系统模板 `sym-lib-table`、`fp-lib-table` 复制到此前没有这两个文件的 `/home/xiaobao/.config/kicad/10.0/`。未覆盖已有用户设置。两张表使用 `KICAD10_SYMBOL_DIR`、`KICAD10_FOOTPRINT_DIR` 变量；按 RPM 标准路径检查，223 个符号库和 155 个封装库全部存在。

## 已完成的环境检查

使用 RPM 自带的 `ecc83` 示例副本，工作目录为仓库内已忽略的 `build/kicad-smoke/`。示例仅用于检查工具链，不是 ESPaperPlay 的电路设计。

| 项目 | 结果 |
| --- | --- |
| 原理图 PDF 导出 | 成功生成 `schematic.pdf` |
| PCB Gerber 导出 | 成功生成两层铜、两层阻焊、顶层丝印和板框文件 |
| ERC | 成功生成 `erc.json`，0 条违规 |
| DRC | 成功生成 `drc.json`，0 个未连接项、0 个错误、2 个丝印与板边间距警告 |
| 项目管理器 | 重启后直接进入主窗口，首次启动向导已完成 |
| 原理图与 PCB 编辑器 | 两者均成功打开示例副本，截图确认图纸、器件与布线显示正常 |
| 3D 渲染 | `kicad-cli pcb render` 成功生成 `demo-3d.png`，已目视确认 PCB 与示例器件模型 |
| 桌面交互与 3D 查看器 | 修复控制脚本后，在左侧屏幕实测鼠标打开菜单、Esc/Alt+3 快捷键、3D 查看器滚轮和拖动旋转成功 |

DRC 的两条警告来自未修改的示例，不是安装失败；也不能把这次检查当成新主板的 ERC/DRC 验收。新板尚无可供验收的原理图或 PCB。

复查命令（在仓库根目录运行；示例副本已存在）：

```sh
kicad-cli version
rpm -q kicad kicad-packages3d kicad-doc
kicad-cli sch export pdf -o build/kicad-smoke/schematic.pdf build/kicad-smoke/ecc83/ecc83-pp.kicad_sch
kicad-cli sch erc --format json -o build/kicad-smoke/erc.json build/kicad-smoke/ecc83/ecc83-pp.kicad_sch
kicad-cli pcb drc --format json -o build/kicad-smoke/drc.json build/kicad-smoke/ecc83/ecc83-pp.kicad_pcb
kicad-cli pcb export gerbers -o build/kicad-smoke/gerbers/ -l F.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,Edge.Cuts build/kicad-smoke/ecc83/ecc83-pp.kicad_pcb
kicad-cli pcb render --width 1200 --height 900 --quality basic --rotate 325,0,25 -o build/kicad-smoke/demo-3d.png build/kicad-smoke/ecc83/ecc83-pp.kicad_pcb
```

以上 ERC/DRC 命令用于确认工具可运行；默认退出码不代表规则零违规。对正式设计设置验收时，应检查报告，并根据规则使用 `--exit-code-violations`。

## 重启后的检查与边界

用户已自行安装嘉立创 EDA，并于 2026-11-01 告知已按安装脚本提示重启。重启后完成上述管理器、原理图编辑器、PCB 编辑器与命令行 3D 渲染检查。标准库配置仍存在。

首次 RemoteDesktop Portal 连接曾返回 `org.freedesktop.DBus.Error.UnknownMethod`。进一步检查发现本地 `local-desktop` 脚本在连接失败后的清理过程中，会用 Session.Close 错误覆盖原始异常；旧日志不足以还原最初是超时还是其他失败。这不是已证实的 KiCad 或 Portal 服务故障。

2026-11-01 已修复该脚本：容忍清理时会话已经消失，保留原始失败原因并报告失败阶段，其他清理错误单独输出，不自动重试授权。5 项会话回归测试和原有 3 项输入释放测试通过，技能校验通过。用户重新完成系统授权后连接成功，在 KiCad 示例副本上完成菜单点击、快捷键、交互式 3D 查看器缩放与旋转测试，测试后关闭控制会话。

按用户要求，后续本项目工作窗口放在左侧 `eDP-1`。本次屏幕布局为左侧 1920×1080、原点 `(0,187)`，右侧 2560×1440、原点 `(1920,0)`，缩放均为 1。已将 KiCad 管理器、原理图和 PCB 编辑器移到左侧，3D 查看器也在左侧打开。以后每次连接仍需核对实际布局和 Portal stream 尺寸，不能把本次坐标视为永久配置。

用户提供的旧版嘉立创工程已另行接收，见 [旧工程记录](legacy-project.md)；尚未导入或转换为 KiCad 工程，也未安装第三方元件插件。屏幕与触摸资料见 [panel-reference.md](panel-reference.md)，其余器件选型和原理图设计保持待定。
