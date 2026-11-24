# Comic Global Coordinate Stream（漫画全局坐标流）

这是一个 Codex Skill 与 Python 工具集，用于把按顺序保存的漫画或条漫切片转换成确定性的全局 Y 坐标系。

它把三个容易混淆的环节严格分开：

- 原始图片像素的唯一归属；
- 供人工检查使用、允许重叠的阅读扫描图；
- 从来源像素精确重建的最终区域。

## 为什么需要它

长篇漫画章节经常由数百张编号图片组成。如果每次裁切都绑定某一张文件，跨图画格、边界调整和重复执行很容易失控。本项目在保留完整来源映射的前提下，为所有切片建立连续坐标空间，并校验每个边界和重复运行结果。

## 主要能力

- 严格按数字顺序发现源文件，并检测编号缺口
- 可选的宽度标准化，默认不放大小图
- 基于解码像素的保守边界去重
- 无重叠的像素归属核心区，以及带上下文的阅读扫描图
- 使用半开区间全局坐标执行跨源提取
- 独立的解码像素审计
- 可重复运行的合成冒烟测试

## 前置条件

- Python 3.10+
- 支持 `ImageCms` 的 Pillow 12.3.0 或更新的 12.x 版本

安装或升级依赖（已有环境也需要执行）：

```bash
python -m pip install --upgrade -r requirements.txt
```

版本下限用于排除 Pillow 12.3.0 之前已披露的 `ImageCms` 和裁切相关越界写入问题，参见 [ImageCms 安全公告](https://github.com/advisories/GHSA-9hw9-ch79-4vh6)与[裁切安全公告](https://github.com/advisories/GHSA-6r8x-57c9-28j4)。这不表示本工具已证实存在可利用路径；处理外部图片前仍应更新依赖，并限制输入规模。Pillow 13 尚未验证，因此暂不纳入支持范围。

## 作为 Codex Skill 使用

将本仓库克隆或复制到个人 Codex Skill 目录，并保持目录名为 `comic-global-coordinate-stream`，然后调用：

```text
$comic-global-coordinate-stream
```

完整工作流程见 `SKILL.md`，坐标和验证不变量见 `references/specification.md`。

## 直接运行脚本

同一章节需要构建两次。第一次应报告 `PENDING_RERUN`；输入不变的第二次必须报告 `PASS`。

输入图片必须保存在当前章节输出目录 `output-root/chapters/<chapter>` 之外。重新构建会清理该章节的 `scans` 和索引文件；工具会在清理前拒绝与输入目录或解析后源文件重叠的布局，避免误删输入。建议把原图放在独立的 `input/` 目录。

```bash
python scripts/canonicalize_chapter.py \
  --chapter ch_001 \
  --input-dir ./examples/input/ch_001 \
  --output-root ./work/canonical \
  --extension .jpg \
  --width 690 \
  --width-policy strict \
  --core-height 6000 \
  --context 3000 \
  --view-height 12000
```

提取可能跨越多个源文件的区域：

```bash
python scripts/extract_global_region.py \
  --canonical-root ./work/canonical \
  --chapter ch_001 \
  --x0 0 --x1 690 \
  --global-y0 12000 --global-y1 18000 \
  --output ./work/shots/shot.png
```

执行独立审计：

```bash
python scripts/audit_output.py \
  --canonical-root ./work/canonical \
  --chapter ch_001
```

## 验证

```bash
python -m unittest -v tests.test_smoke tests.test_input_safety
```

测试会在临时目录中生成合成图片，连续执行两次标准化构建，最后运行独立像素审计。输入安全测试还验证：章节输出目录、`scans` 及其子目录内的输入会被提前拒绝，源图片和已有输出逐字节保持不变；输出根目录下其他位置的输入仍可正常构建。

## 目录结构

```text
agents/       Codex Skill 元数据
assets/       可复用配置与金标准摘要
references/   坐标与验证契约
scripts/      标准化、提取、审计和夹具生成脚本
tests/        端到端确定性冒烟测试
SKILL.md      Codex Skill 指令
```

## 已知限制

- 本项目不执行 OCR、画格检测、剧情分析或内容选择。
- 解码像素比较刻意采用保守策略，可能保留无法确认的重复行。
- 大型章节需要足够空间保存扫描图和临时标准化图片。
- 金标准摘要只记录预期指标，不包含受版权保护的漫画源图。

## 来源

项目来自 2026-08-19 的 Codex 辅助工作流，并于 2026-08-27 整理为干净公开副本。仓库不包含私人输入、生成漫画、本机路径或对话历史。

## 许可证

本仓库目前没有授予开源许可证。没有许可证意味着默认版权限制仍然有效。
