"""
RZ Automedata - Video Utilities
Extract frames from video files for AI analysis.
"""

import cv2
import os
from PIL import Image
import numpy as np


def extract_frames(video_path, num_frames=None, max_frames=15):
    """
    Extract frames from a video file — 1 frame per second.
    
    Args:
        video_path: Path to the video file (MP4, MOV)
        num_frames: Override number of frames (if None, uses 1 per second)
        max_frames: Maximum frames to extract (default: 10)
    
    Returns:
        List of PIL.Image objects
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video file: {video_path}")
    
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    duration_sec = total_frames / fps
    
    if total_frames <= 0:
        cap.release()
        raise ValueError(f"Video has no frames: {video_path}")
    
    if num_frames is not None:
        # Legacy: fixed number of evenly spaced frames
        count = min(num_frames, total_frames)
        frame_indices = [int(i * (total_frames - 1) / max(count - 1, 1)) for i in range(count)]
    else:
        # 1 frame per second, capped at max_frames
        duration_int = max(1, int(duration_sec))
        if duration_int <= max_frames:
            # Short video: 1 frame per second
            count = duration_int
            frame_indices = []
            for sec in range(count):
                frame_idx = int(sec * fps)
                frame_indices.append(min(frame_idx, total_frames - 1))
        else:
            # Long video: spread max_frames evenly across full duration
            count = max_frames
            frame_indices = []
            for i in range(count):
                sec = i * duration_sec / count
                frame_idx = int(sec * fps)
                frame_indices.append(min(frame_idx, total_frames - 1))
    
    frames = []
    for idx in frame_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if ret:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(frame_rgb)
            frames.append(pil_image)
    
    cap.release()
    return frames


def get_video_thumbnail(video_path, size=(200, 150)):
    """
    Get a single thumbnail from the middle of the video for preview.
    
    Args:
        video_path: Path to the video file
        size: Thumbnail size tuple (width, height)
    
    Returns:
        PIL.Image object (thumbnail)
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video file: {video_path}")
    
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    middle_frame = total_frames // 2
    
    cap.set(cv2.CAP_PROP_POS_FRAMES, middle_frame)
    ret, frame = cap.read()
    cap.release()
    
    if not ret:
        raise ValueError(f"Cannot read frame from video: {video_path}")
    
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    pil_image = Image.fromarray(frame_rgb)
    pil_image.thumbnail(size, Image.LANCZOS)
    return pil_image
