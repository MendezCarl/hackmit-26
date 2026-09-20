"""Zoom Realtime Media Streams (RTMS) transcript integration.

Provider-specific protocol handling stays inside this package. Only typed
``TranscriptChunk`` records cross into the application transcript service;
raw audio and video media types are never requested.
"""
