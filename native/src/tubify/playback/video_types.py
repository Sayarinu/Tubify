"""Which tracks have a music video, without loading Qt Quick."""

VIDEO_TYPES = {"MUSIC_VIDEO_TYPE_OMV", "MUSIC_VIDEO_TYPE_UGC", "MUSIC_VIDEO_TYPE_OFFICIAL_SOURCE_MUSIC"}


def has_video(track):
    return (track or {}).get("videoType") in VIDEO_TYPES
