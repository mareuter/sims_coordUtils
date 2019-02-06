from lsst.obs.lsst.phosim import PhosimMapper
import lsst.log as lsstLog


__all__ = ["lsst_camera"]


def lsst_camera():
    """
    Return a copy of the LSST Camera model as stored in obs_lsstSim.
    """
    if not hasattr(lsst_camera, '_lsst_camera'):
        lsstLog.setLevel('CameraMapper', lsstLog.WARN)
        lsst_camera._lsst_camera = PhosimMapper().camera

    return lsst_camera._lsst_camera
