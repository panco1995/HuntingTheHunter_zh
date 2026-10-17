# Hunting The Hunter 简体中文补丁

适用于当前 Steam 版本，商店地址：https://store.steampowered.com/app/2408880/Hunting_The_Hunter/

## 效果预览

主菜单：

![汉化后的主菜单](screenshots/20261018030152_1.jpg)

剧情画面：

![汉化后的剧情文字](screenshots/20261018030201_1.jpg)

## 安装

1. 复制 `dist`目录下`Hunting The Hunter_Data` 整个文件夹到游戏根目录覆盖原文件（可直接下载HuntingTheHunter_zh.zip解压）

## 卸载

在 Steam 中执行 `验证游戏文件的完整性` 恢复英文版。

## 补丁内容

- 菜单、按钮、开关和故事正文简体中文化。
- 同时修改 PlayMaker 状态机中的运行时标签，避免操作后恢复英文。
- 将原游戏不含中文字形的 Lilita One 字体替换为经过裁剪的特粗中文字体，并放大正文与按钮字号。
- 不修改可执行文件和游戏程序集。

## 重新构建补丁文件

需要 Python 3。先安装构建依赖：

```powershell
python -m pip install -r .\requirements.txt
```

```powershell
python .\tools\scan_assets.py "..\Hunting The Hunter_Data" ".\work"
python .\tools\prepare_font.py "C:\Windows\Fonts\NotoSansSC-VF.ttf" `
  ".\translations.zh-CN.json" ".\work\text_candidates.tsv" `
  ".\font\HTH-Chinese.ttf"
python .\tools\build_patch.py "..\Hunting The Hunter_Data" `
  ".\translations.zh-CN.json" ".\dist"
```

## 字体许可

补丁字体基于 Noto Sans SC，并经过字符裁剪及重命名。字体依据 SIL Open
Font License 1.1 使用和再分发，完整条款见 `FONT-LICENSE.txt`。
