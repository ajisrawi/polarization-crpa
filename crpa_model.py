"""
Signal model for a polarization-sensitive GNSS antenna array (CRPA).

Coordinates
-----------
The array lies in the x-y plane (x = east, y = north), z points to zenith.
Directions are given as elevation / azimuth (azimuth clockwise from north).
Internally theta = zenith angle, phi = math angle from the x axis.

Polarization
------------
An incoming wave's polarization is a Jones vector (E_theta, E_phi).
Each antenna port has a receive vector h = (h_theta, h_phi); the port's
output voltage is h . E (no conjugation). A port is matched to the wave conj(h).

Wideband
--------
Every emitter is generated in the frequency domain, so true time delays across
the aperture and per-channel RF mismatch (gain, phase, delay, filter ripple)
are modelled exactly over the band.
"""
from dataclasses import dataclass, field

import numpy as np

C = 299_792_458.0
F_L1 = 1575.42e6
LAMBDA_L1 = C / F_L1


# --------------------------------------------------------------------------
# Wave polarization states (Jones vectors in the theta / phi basis)
# --------------------------------------------------------------------------

def jones_rhcp():
    return np.array([1.0, -1.0j]) / np.sqrt(2)


def jones_lhcp():
    return np.array([1.0, 1.0j]) / np.sqrt(2)


def jones_linear(tilt_deg):
    """Linear polarization. tilt 0 = vertical (E along theta_hat), 90 = horizontal."""
    t = np.radians(tilt_deg)
    return np.array([np.cos(t), np.sin(t)], dtype=complex)


def jones_elliptical(tilt_deg, ellipticity_deg):
    """General polarization: orientation angle and ellipticity angle (+45 = RHCP)."""
    t, e = np.radians(tilt_deg), np.radians(ellipticity_deg)
    base = np.array([np.cos(e), -1j * np.sin(e)])
    rot = np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])
    return rot @ base


# --------------------------------------------------------------------------
# Antenna port models
# --------------------------------------------------------------------------

def _patch_cuts(theta):
    """E- and H-plane field patterns of a patch over a ground plane.

    theta is measured from the patch boresight. Behind the ground plane the
    pattern falls to a -20 dB back lobe.
    """
    c = np.cos(theta)
    cf = np.clip(c, 0.0, None)
    cb = np.clip(-c, 0.0, None)
    f_e = np.where(c >= 0, 0.5 * (1.0 + cf), 0.5 - 0.4 * cb)  # E-plane radiates at grazing
    f_h = np.where(c >= 0, cf ** 0.8, 0.1 * cb ** 0.8)       # H-plane is zero at grazing
    return f_e, f_h


def _linear_patch(theta, phi, orient):
    f_e, f_h = _patch_cuts(theta)
    p = phi - orient
    return np.stack([np.cos(p) * f_e, -np.sin(p) * f_h])


def port_vector(kind, theta, phi, orient=0.0):
    """
    Receive vector (2, ...) of one antenna port.

    kind:
      'X', 'Y' : the two orthogonal linear feeds of a dual-feed patch
      'R', 'L' : RHCP / LHCP ports of a dual-feed patch (hybrid outputs)
      'H'      : single linear patch (feed direction = orient). It is horizontally
                 polarized only for sources in its H-plane; in its E-plane at low
                 elevation it behaves like a vertical antenna.
      'V'      : vertical quarter-wave monopole on the ground plane
    """
    if kind in ("X", "H"):
        return _linear_patch(theta, phi, orient)
    if kind == "Y":
        return _linear_patch(theta, phi, orient + np.pi / 2)
    if kind in ("R", "L"):
        x = _linear_patch(theta, phi, orient)
        y = _linear_patch(theta, phi, orient + np.pi / 2)
        s = 1j if kind == "R" else -1j
        return (x + s * y) / np.sqrt(2)
    if kind == "V":
        return np.stack([-np.sin(theta), np.zeros_like(theta)])
    raise ValueError(f"unknown port kind {kind!r}")


def _with_cross_pol(h, eps):
    """Add a leakage term matched to the polarization orthogonal to the port's own."""
    orth = np.stack([-np.conj(h[1]), np.conj(h[0])])
    return h + eps * orth


def direction(el_deg, az_deg):
    """Return (theta, phi, unit vector toward the source) for el/az in degrees."""
    el, az = np.radians(el_deg), np.radians(az_deg)
    theta = np.pi / 2 - el
    phi = np.pi / 2 - az
    u = np.stack([np.cos(el) * np.sin(az), np.cos(el) * np.cos(az), np.sin(el)])
    return theta, phi, u


def _spherical_units(theta, phi):
    """theta_hat and phi_hat as (3, ...) Cartesian vectors."""
    t_hat = np.stack([np.cos(theta) * np.cos(phi), np.cos(theta) * np.sin(phi), -np.sin(theta)])
    p_hat = np.stack([-np.sin(phi), np.cos(phi), np.zeros_like(phi)])
    return t_hat, p_hat


def _element_frame(boresight_el_deg, boresight_az_deg):
    """Rows x', y', z' of an element frame whose z' axis is the element boresight."""
    _, _, z = direction(boresight_el_deg, boresight_az_deg)
    az = np.radians(boresight_az_deg)
    x = np.array([np.cos(az), -np.sin(az), 0.0])
    return np.stack([x, np.cross(z, x), z])


def tilted_port_vector(kind, theta, phi, orient, boresight_el_deg, boresight_az_deg):
    """Receive vector (global theta/phi basis) of a port whose boresight is tilted."""
    frame = _element_frame(boresight_el_deg, boresight_az_deg)
    t_hat, p_hat = _spherical_units(theta, phi)
    u = np.stack([np.sin(theta) * np.cos(phi), np.sin(theta) * np.sin(phi), np.cos(theta)])
    ul = np.tensordot(frame, u, axes=(1, 0))
    theta_l = np.arccos(np.clip(ul[2], -1.0, 1.0))
    phi_l = np.arctan2(ul[1], ul[0])
    h_l = port_vector(kind, theta_l, phi_l, orient)
    t_l, p_l = _spherical_units(theta_l, phi_l)
    # local unit vectors -> global Cartesian, then project on the global basis
    e = (np.tensordot(frame.T, t_l, axes=(1, 0)) * h_l[0]
         + np.tensordot(frame.T, p_l, axes=(1, 0)) * h_l[1])
    return np.stack([(e * t_hat).sum(axis=0), (e * p_hat).sum(axis=0)])


# --------------------------------------------------------------------------
# Array configuration
# --------------------------------------------------------------------------

@dataclass
class Port:
    kind: str
    pos: tuple                 # (x, y) in metres
    orient_deg: float = 0.0    # feed direction, math angle from the x axis
    boresight_el_deg: float = 90.0   # 90 = facing zenith (flat on the ground plane)
    boresight_az_deg: float = 0.0


@dataclass
class ArrayConfig:
    name: str
    ports: list
    ref_port: int = 0          # reference channel for power inversion (an RHCP port)
    xpd_db: float = 25.0       # cross-polarization isolation of every port
    seed: int = 0

    def __post_init__(self):
        rng = np.random.default_rng(self.seed)
        self.positions = np.array([[p.pos[0], p.pos[1], 0.0] for p in self.ports])
        self.xpd_eps = 10 ** (-self.xpd_db / 20) * np.exp(2j * np.pi * rng.random(self.n))

    @property
    def n(self):
        return len(self.ports)

    def pol_gain(self, el_deg, az_deg, jones):
        """Complex polarization/pattern gain of every port: shape (N,) + shape(el)."""
        theta, phi, _ = direction(np.asarray(el_deg, float), np.asarray(az_deg, float))
        out = []
        for port, eps in zip(self.ports, self.xpd_eps):
            orient = np.radians(port.orient_deg)
            if port.boresight_el_deg == 90.0:
                h = port_vector(port.kind, theta, phi, orient)
            else:
                h = tilted_port_vector(port.kind, theta, phi, orient,
                                       port.boresight_el_deg, port.boresight_az_deg)
            h = _with_cross_pol(h, eps)
            out.append(h[0] * jones[0] + h[1] * jones[1])
        return np.array(out)

    def delays(self, el_deg, az_deg):
        """Arrival time advance (s) at each port relative to the array origin."""
        _, _, u = direction(np.asarray(el_deg, float), np.asarray(az_deg, float))
        return np.tensordot(self.positions, u, axes=(1, 0)) / C


def reference_rhcp_gain(el_deg, az_deg, jones):
    """Gain of a single ideal RHCP patch (the 'no anti-jam' reference receiver)."""
    theta, phi, _ = direction(np.asarray(el_deg, float), np.asarray(az_deg, float))
    h = port_vector("R", theta, phi)
    return h[0] * jones[0] + h[1] * jones[1]


# --------------------------------------------------------------------------
# Emitters, RF channel errors and the receiver front end
# --------------------------------------------------------------------------

@dataclass
class Emitter:
    el_deg: float
    az_deg: float
    jones: np.ndarray
    power_db: float = 0.0   # power in a unity-gain port, relative to receiver noise
    bw_hz: float = 8e6
    f0_hz: float = 0.0
    cw: bool = False
    label: str = ""


@dataclass
class ChannelErrors:
    gain_db_std: float = 0.5
    phase_deg_std: float = 5.0
    delay_ns_std: float = 1.0
    ripple_db: float = 0.2
    cal_gain_db_std: float = 0.2   # residual error of the calibration used by MVDR
    cal_phase_deg_std: float = 2.0


class Receiver:
    """N coherent RF channels sampled at complex baseband around L1."""

    def __init__(self, array, fs=10e6, n_samples=2 ** 15, errors=None, seed=1):
        self.array = array
        self.fs = fs
        self.k = n_samples
        self.freqs = np.fft.fftfreq(n_samples, 1 / fs)
        self.errors = errors or ChannelErrors()
        rng = np.random.default_rng(seed)
        self.h_mis = self._mismatch(rng)
        self.eq = np.ones_like(self.h_mis)
        e = self.errors
        self.cal_err = (10 ** (rng.normal(0, e.cal_gain_db_std, array.n) / 20)
                        * np.exp(1j * np.radians(rng.normal(0, e.cal_phase_deg_std, array.n))))

    @property
    def chan(self):
        """Effective RF-chain frequency response after equalization: (N, F)."""
        return self.h_mis * self.eq

    def equalize(self, cal_snr_db=30.0, fir_taps=64, seed=2):
        """Per-channel FIR equalization from a calibration-noise injection.

        A noise source injected behind the antennas is measured in every channel
        (per-bin accuracy cal_snr_db). The inverse response is truncated to a
        fir_taps-long FIR, as a real equalizer would be, which also averages the
        measurement noise down by sqrt(n_samples / fir_taps).
        """
        rng = np.random.default_rng(seed)
        meas_err = 10 ** (-cal_snr_db / 20) * (rng.standard_normal(self.h_mis.shape)
                                                + 1j * rng.standard_normal(self.h_mis.shape)) / np.sqrt(2)
        impulse = np.fft.ifft(1 / (self.h_mis * (1 + meas_err)), axis=1)
        impulse[:, fir_taps // 2:-fir_taps // 2] = 0  # keep taps -L/2 .. L/2-1 (circular)
        self.eq = np.fft.fft(impulse, axis=1)
        return self

    def _mismatch(self, rng):
        e, n, f = self.errors, self.array.n, self.freqs
        g = 10 ** (rng.normal(0, e.gain_db_std, n) / 20)
        ph = np.radians(rng.normal(0, e.phase_deg_std, n))
        d = rng.normal(0, e.delay_ns_std, n) * 1e-9
        a = e.ripple_db / 8.686
        period = rng.uniform(1e6, 5e6, n)
        psi = rng.uniform(0, 2 * np.pi, n)
        ripple = 1 + a * np.cos(2 * np.pi * f[None, :] / period[:, None] + psi[:, None])
        return (g * np.exp(1j * ph))[:, None] * np.exp(-2j * np.pi * f[None, :] * d[:, None]) * ripple

    def response(self, em):
        """True per-channel frequency response to an emitter: (N, F)."""
        g = self.array.pol_gain(em.el_deg, em.az_deg, em.jones)
        tau = self.array.delays(em.el_deg, em.az_deg)
        geo = np.exp(2j * np.pi * (F_L1 + self.freqs)[None, :] * tau[:, None])
        return g[:, None] * geo * self.chan

    def assumed_steering(self, em):
        """Steering vector the processor believes in (calibrated, centre frequency)."""
        return self.response(em)[:, 0] * self.cal_err

    def psd_shape(self, em):
        """Emitter PSD on the FFT grid, normalized so that its mean is 1."""
        s = np.zeros(self.k)
        if em.cw:
            s[np.argmin(np.abs(self.freqs - em.f0_hz))] = self.k
        else:
            band = np.abs(self.freqs - em.f0_hz) <= em.bw_hz / 2
            s[band] = self.k / band.sum()
        return s

    def generate(self, jammers, rng):
        """Complex baseband samples (N, K): jammers + unit-power receiver noise.

        GNSS signals are ~20-30 dB below the noise floor, so they do not shape the
        covariance and are left out of the samples; they are scored analytically.
        """
        n, k = self.array.n, self.k
        spec = np.zeros((n, k), complex)
        for em in jammers:
            p = 10 ** (em.power_db / 10)
            s = self.psd_shape(em)
            if em.cw:
                src = np.sqrt(k * p * s) * np.exp(2j * np.pi * rng.random())
            else:
                src = np.sqrt(k * p * s) * (rng.standard_normal(k) + 1j * rng.standard_normal(k)) / np.sqrt(2)
            spec += self.response(em) * src[None, :]
        noise = (rng.standard_normal((n, k)) + 1j * rng.standard_normal((n, k))) * np.sqrt(k / 2)
        spec += noise * self.eq  # receiver noise also passes through the equalizer
        return np.fft.ifft(spec, axis=1)
