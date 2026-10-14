import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from app.enhancers.temporal import TemporalStabilizer  # noqa: E402


def _texture(height: int, width: int, seed: int = 0):
    """Smooth random texture (something the optical flow can track)."""
    rng = np.random.default_rng(seed)
    small = rng.integers(0, 255, (height // 8, width // 8, 3), dtype=np.uint8)
    return cv2.GaussianBlur(
        cv2.resize(small, (width, height), interpolation=cv2.INTER_CUBIC), (0, 0), 2
    )


def _upscale(image):
    return cv2.resize(image, None, fx=2, fy=2, interpolation=cv2.INTER_LANCZOS4)


@pytest.mark.parametrize(
    # Filtro recursivo con α = intensidad × 0,8: el ruido estable baja a √((1-α)/(1+α)).
    ("strength", "max_ratio"),
    [(0.5, 0.72), (1.0, 0.45)],
)
def test_static_scene_shimmer_is_reduced(strength, max_ratio) -> None:
    stabilizer = TemporalStabilizer(strength)
    rng = np.random.default_rng(1)
    source = _texture(96, 128)
    clean = _upscale(source).astype(np.float32)
    raw, stabilized = [], []
    for _ in range(20):
        # La IA "hierve": la misma escena con detalle inventado distinto en cada fotograma.
        noisy = np.clip(clean + rng.normal(0, 12, clean.shape), 0, 255).astype(np.uint8)
        raw.append(noisy.astype(np.float32))
        stabilized.append(stabilizer.apply(source, noisy).astype(np.float32))

    def temporal_std(frames):
        return float(np.stack(frames[5:]).std(axis=0).mean())

    assert temporal_std(stabilized) < max_ratio * temporal_std(raw)


def test_moving_content_follows_the_motion_without_ghosting() -> None:
    stabilizer = TemporalStabilizer(1.0)
    canvas = _texture(160, 220, seed=3)
    errors = []
    for step in range(12):
        # La cámara se desplaza 2 px por fotograma: la salida debe seguirla, sin estela.
        source = np.ascontiguousarray(canvas[16:112, step * 2 : step * 2 + 128])
        expected = _upscale(source)
        output = stabilizer.apply(source, expected)
        errors.append(float(np.abs(output.astype(np.float32) - expected).mean()))

    assert max(errors) < 3.0


def test_scene_change_resets_the_history() -> None:
    stabilizer = TemporalStabilizer(1.0)
    first = _texture(96, 128, seed=1)
    stabilizer.apply(first, _upscale(first))
    other = np.full((96, 128, 3), 235, dtype=np.uint8)
    other[20:70, 30:90] = (10, 40, 200)

    output = stabilizer.apply(other, _upscale(other))

    assert np.array_equal(output, _upscale(other))
    assert stabilizer.resets == 1


def test_strength_zero_is_a_no_op() -> None:
    stabilizer = TemporalStabilizer(0)
    source = _texture(48, 64)
    stabilizer.apply(source, _upscale(source))
    noisy = np.clip(_upscale(source).astype(int) + 20, 0, 255).astype(np.uint8)

    assert np.array_equal(stabilizer.apply(source, noisy), noisy)
