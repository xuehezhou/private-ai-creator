# -*- coding: utf-8 -*-
"""
audio.py —— BGM 节奏感知截取模块 (可选依赖)
=============================================
功能：分析音频能量/节拍，找到节奏连贯的截取起点，裁出指定时长并加淡入淡出。
依赖：pydub + numpy + imageio-ffmpeg（pip install，后者自带 ffmpeg 二进制）
无依赖时 HAS_AUDIO=False，调用 trim_bgm 返回空串（安全降级，不影响主流程）。
"""
import os
import subprocess
import tempfile

try:
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        from pydub import AudioSegment
    import numpy as np
    # imageio-ffmpeg 自带静态 ffmpeg 二进制，免去系统级安装
    try:
        import imageio_ffmpeg
        _ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        AudioSegment.converter = _ffmpeg_exe
    except (ImportError, Exception):
        _ffmpeg_exe = None
    HAS_AUDIO = True
except ImportError:
    HAS_AUDIO = False
    _ffmpeg_exe = None


def _load_audio(audio_path):
    """加载任意格式音频为 AudioSegment。
    wav 走 pydub 内置纯 Python 读取（无需外部工具）；
    其他格式用 ffmpeg 解码为临时 wav 再读取（绕过 ffprobe 依赖）。"""
    ext = os.path.splitext(audio_path)[1].lower().lstrip(".")
    if ext == "wav":
        return AudioSegment.from_wav(audio_path)
    # 非 wav：用 ffmpeg 解码为 16-bit PCM wav（不需要 ffprobe）
    if not _ffmpeg_exe:
        raise RuntimeError("ffmpeg not available for non-wav decode")
    tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_path = tmp_wav.name
    tmp_wav.close()
    try:
        cmd = [_ffmpeg_exe, "-y", "-i", audio_path,
               "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2", tmp_path]
        subprocess.run(cmd, capture_output=True, timeout=60, check=True)
        return AudioSegment.from_wav(tmp_path)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _energy_onsets(audio, hop_ms=50):
    """计算每 hop_ms 的 RMS 能量，返回 (rms_array, hop_samples)"""
    raw = audio.get_array_of_samples()
    samples = np.array(raw, dtype=np.float64)
    if audio.channels == 2:
        samples = samples.reshape(-1, 2).mean(axis=1)
    sr = audio.frame_rate
    hop = int(sr * hop_ms / 1000)
    n = len(samples) // hop
    if n < 2:
        return np.array([0.0]), hop
    # 逐帧 RMS
    reshaped = samples[:n * hop].reshape(n, hop)
    rms = np.sqrt(np.mean(reshaped ** 2, axis=1))
    return rms, hop


def _find_best_start_ms(audio, target_ms, min_skip_ms=3000):
    """找最佳截取起点：能量上升沿（乐句/节拍起始），跳过开头空白/前奏"""
    rms, hop = _energy_onsets(audio, hop_ms=50)
    if len(rms) < 10:
        return 0
    # 一阶差分 = onset 强度
    onset = np.diff(rms)
    threshold = np.mean(onset) + 0.6 * np.std(onset)
    candidates = np.where(onset > threshold)[0]
    # 至少跳过 min_skip_ms（避免截到前奏静音）
    min_frame = int(min_skip_ms / 50)
    candidates = candidates[candidates > min_frame]
    # 必须留够 target_ms 的空间
    max_frame = len(rms) - int(target_ms / 50) - 1
    candidates = candidates[candidates < max_frame]
    if len(candidates) == 0:
        # 退而求其次：从 min_skip 开始
        return min_skip_ms
    # 选第一个强 onset（最早的乐句起始）
    return int(candidates[0] * 50)


def trim_bgm(audio_path, duration_sec=30, out_path="", fade_ms=80):
    """分析节奏 → 找最佳起点 → 截取 duration_sec 秒 → 淡入淡出 → 保存。
    返回 out_path（成功）或 ""（失败/无依赖/无文件）。"""
    if not HAS_AUDIO:
        return ""
    if not audio_path or not os.path.exists(audio_path):
        return ""
    try:
        audio = _load_audio(audio_path)
    except Exception:
        return ""
    target_ms = duration_sec * 1000
    if len(audio) <= target_ms:
        # 音频本身比目标短，直接用全长（加淡入淡出）
        start_ms = 0
        clip = audio
    else:
        start_ms = _find_best_start_ms(audio, target_ms)
        clip = audio[start_ms:start_ms + target_ms]
    # 淡入淡出保证连贯
    clip = clip.fade_in(min(fade_ms, len(clip) // 4)).fade_out(min(fade_ms, len(clip) // 4))
    if not out_path:
        return ""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    try:
        clip.export(out_path, format="mp3", bitrate="128k")
    except Exception:
        # mp3 编码失败时试 wav
        try:
            out_path = out_path.rsplit(".", 1)[0] + ".wav"
            clip.export(out_path, format="wav")
        except Exception:
            return ""
    return out_path


def find_bgm_files(bg_dir):
    """扫描 BGM 文件夹，返回音频文件路径列表"""
    if not os.path.isdir(bg_dir):
        return []
    exts = (".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac")
    return [os.path.join(bg_dir, f) for f in sorted(os.listdir(bg_dir))
            if f.lower().endswith(exts)]
