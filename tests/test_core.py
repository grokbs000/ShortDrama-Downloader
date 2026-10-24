from resolver.detector import score_url
from resolver.hls import _attrs

def test_mp4_scores():
    assert score_url("https://x.test/a.mp4","video/mp4",10_000_000) > score_url("https://x.test/thumb.jpg","image/jpeg",1000)

def test_hls_attrs():
    x=_attrs('BANDWIDTH=1000000,RESOLUTION="1280x720",FRAME-RATE=30')
    assert x["BANDWIDTH"]=="1000000"
    assert x["RESOLUTION"]=="1280x720"
