"""
Space-polarization-time adaptive processing (STAP) for a polarization-sensitive CRPA.

The processor sees only the raw channel samples. Weights are computed from the
sample covariance, so polarization and spatial degrees of freedom are used
together automatically: the array cancels each jammer in whatever combination of
direction and polarization is cheapest for the satellites.

Weight layout: index n * taps + m multiplies x_n[k - m]; output y[k] = w^H z[k].
"""
import numpy as np

from crpa_model import F_L1, reference_rhcp_gain


# --------------------------------------------------------------------------
# Adaptive weights
# --------------------------------------------------------------------------

def snapshots(x, taps):
    """Space-time snapshot matrix (N*taps, K) from channel samples (N, K)."""
    n, k = x.shape
    z = np.empty((n, taps, k), complex)
    for m in range(taps):
        z[:, m] = np.roll(x, m, axis=1)
    return z.reshape(n * taps, k)


def sample_covariance(z):
    return (z @ z.conj().T) / z.shape[1]


def _loaded(r, loading):
    return r + loading * np.eye(r.shape[0])


def power_inversion(r, ref_port, taps, loading=0.1):
    """Blind minimum-power beamformer: minimize w^H R w subject to w^H e_ref = 1.

    Needs no knowledge of satellites, attitude or array calibration.
    """
    e = np.zeros(r.shape[0], complex)
    e[ref_port * taps + taps // 2] = 1.0
    ri_e = np.linalg.solve(_loaded(r, loading), e)
    return ri_e / (e.conj() @ ri_e)


def st_steering(a, taps):
    """Space-time constraint vector: spatial-polarization steering on the centre tap."""
    c = np.zeros(a.size * taps, complex)
    c[np.arange(a.size) * taps + taps // 2] = a
    return c


def mvdr(r, steering, loading=0.1):
    """MVDR / Capon beam(s): unit gain toward each steering vector, minimum power.

    steering: (D,) or (D, S) for S satellites. Returns weights of the same shape.
    """
    ri_c = np.linalg.solve(_loaded(r, loading), steering)
    return ri_c / np.einsum("i...,i...->...", steering.conj(), ri_c)


# --------------------------------------------------------------------------
# Scoring (exact, in the frequency domain, using the true channel responses)
# --------------------------------------------------------------------------

def _channel_filters(w, rx, taps, freqs=None):
    """Per-channel FIR frequency responses of the weights: (N, F)."""
    freqs = rx.freqs if freqs is None else freqs
    wm = w.reshape(rx.array.n, taps)
    delay = np.exp(-2j * np.pi * np.outer(np.arange(taps), freqs) / rx.fs)
    return wm.conj() @ delay


def evaluate(rx, w, taps, jammers, satellites, band_hz=1.023e6, cn0_ref=45.0):
    """
    Score beamformer weights.

    w: one weight vector for all satellites, or (D, S) with one beam per satellite.
    cn0_ref: C/N0 of a satellite seen with 0 dBic gain and no interference.
    Jammer power inside the GNSS band is treated as extra white noise.
    """
    inband = np.abs(rx.freqs) <= band_hz
    freqs, eq = rx.freqs[inband], rx.eq[:, inband]
    jam_terms = [(rx.response(em)[:, inband], (10 ** (em.power_db / 10) * rx.psd_shape(em))[inband])
                 for em in jammers]
    per_sat = w.ndim == 2
    out = {"cn0": [], "inr_out_db": []}
    for i, sat in enumerate(satellites):
        wi = w[:, i] if per_sat else w
        if i == 0 or per_sat:
            filt = _channel_filters(wi, rx, taps, freqs)
            noise = (np.abs(filt * eq) ** 2).sum(axis=0).mean()
            jam = sum((psd * np.abs((filt * resp).sum(axis=0)) ** 2).mean() for resp, psd in jam_terms)
            out["inr_out_db"].append(10 * np.log10(jam / noise + 1e-30))
        hs = (filt * rx.response(sat)[:, inband]).sum(axis=0)
        gs = (np.abs(hs) ** 2).mean()
        out["cn0"].append(cn0_ref + 10 * np.log10(gs / (noise + jam)))
    out["cn0"] = np.array(out["cn0"])
    out["inr_out_db"] = float(np.max(out["inr_out_db"]))
    return out


def unprotected(rx, jammers, satellites, band_hz=1.023e6, cn0_ref=45.0):
    """A single ordinary RHCP patch with no anti-jam processing."""
    inband = np.abs(rx.freqs) <= band_hz
    inr = sum((10 ** (em.power_db / 10) * rx.psd_shape(em)
               * np.abs(reference_rhcp_gain(em.el_deg, em.az_deg, em.jones)) ** 2)[inband].mean()
              for em in jammers)
    g = np.array([np.abs(reference_rhcp_gain(s.el_deg, s.az_deg, s.jones)) ** 2 for s in satellites])
    return {"inr_in_db": 10 * np.log10(inr + 1e-30),
            "cn0_clean": cn0_ref + 10 * np.log10(g),
            "cn0": cn0_ref + 10 * np.log10(g / (1 + inr))}


def sky_gain(rx, w, taps, jones, el_grid, az_grid):
    """Output SNR gain (dB) at the centre frequency over the sky for one polarization."""
    filt0 = _channel_filters(w, rx, taps)[:, 0]
    noise = (np.abs(filt0 * rx.eq[:, 0]) ** 2).sum()
    ee, aa = np.meshgrid(el_grid, az_grid, indexing="ij")
    g = rx.array.pol_gain(ee, aa, jones)                      # (N, E, A)
    tau = rx.array.delays(ee, aa)                             # (N, E, A)
    a = g * np.exp(2j * np.pi * F_L1 * tau) * rx.chan[:, 0, None, None]
    h = np.tensordot(filt0, a, axes=(0, 0))
    return 10 * np.log10(np.abs(h) ** 2 / noise + 1e-12)
