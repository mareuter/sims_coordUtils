"""
Some of the data in this unit test will appear abitrary.  That is
because, in addition to testing the execution of all of the functionality
provided in the sims_coordUtils package, this unit test validates
the outputs of PALPY against the outputs of pySLALIB v 1.0.2
(it was written when we were making the transition from pySLALIB to PALPY).

There will be some difference, as the two libraries are based on slightly
different conventions (for example, the prenut routine which calculates
the matrix of precession and nutation is based on the IAU 2006/2000A
standard in PALPY and on SF2001 in pySLALIB; however, the two outputs
still agree to within one part in 10^5)

"""

import numpy

import os
import unittest
import warnings
import sys
import math
import palpy as pal
from collections import OrderedDict
import lsst.utils.tests as utilsTests

import lsst.afw.geom as afwGeom
from lsst.sims.catalogs.measures.instance import InstanceCatalog
from lsst.sims.catalogs.generation.db import ObservationMetaData
from lsst.sims.utils import getRotTelPos, raDecFromAltAz, calcObsDefaults, \
                            radiansFromArcsec, arcsecFromRadians, Site
from lsst.sims.coordUtils.Astrometry import AstrometryBase, AstrometryStars, \
                                            AstrometryGalaxies, CameraCoords
from lsst.sims.coordUtils import applyPrecession, applyProperMotion
from lsst.sims.coordUtils import appGeoFromICRS, observedFromAppGeo
from lsst.sims.coordUtils import observedFromICRS, calculatePupilCoordinates
from lsst.sims.coordUtils import refractionCoefficients, applyRefraction
from lsst.sims.coordUtils import calculateGnomonicProjection, calculateFocalPlaneCoordinates
from lsst.sims.coordUtils import findChipName, calculatePixelCoordinates, calculateFocalPlaneCoordinates
from lsst.sims.catalogs.generation.utils import myTestStars, makeStarTestDB, \
                                                myTestGals, makeGalTestDB
import lsst.afw.cameraGeom.testUtils as camTestUtils

def makeObservationMetaData():
    #create a cartoon ObservationMetaData object
    mjd = 52000.0
    alt = numpy.pi/2.0
    az = 0.0
    band = 'r'
    testSite = Site(latitude=0.5, longitude=1.1, height=3000, meanTemperature=260.0,
                    meanPressure=725.0, lapseRate=0.005)
    centerRA, centerDec = raDecFromAltAz(alt,az,testSite.longitude,testSite.latitude,mjd)
    rotTel = getRotTelPos(centerRA, centerDec, testSite.longitude, testSite.latitude, mjd, 0.0)

    obsDict = calcObsDefaults(centerRA, centerDec, alt, az, rotTel, mjd, band,
                 testSite.longitude, testSite.latitude)

    obsDict['Opsim_expmjd'] = mjd
    radius = 0.1
    phoSimMetaData = OrderedDict([
                      (k, (obsDict[k],numpy.dtype(type(obsDict[k])))) for k in obsDict])

    obs_metadata = ObservationMetaData(boundType='circle', boundLength=2.0*radius,
                                       phoSimMetaData=phoSimMetaData, site=testSite)

    return obs_metadata

def makeRandomSample(raCenter=None, decCenter=None, radius=None):
    #create a random sample of object data

    nsamples=100
    numpy.random.seed(32)

    if raCenter is None or decCenter is None or radius is None:
        ra = numpy.random.sample(nsamples)*2.0*numpy.pi
        dec = (numpy.random.sample(nsamples)-0.5)*numpy.pi
    else:
        rr = numpy.random.sample(nsamples)*radius
        theta = numpy.random.sample(nsamples)*2.0*numpy.pi
        ra = raCenter + rr*numpy.cos(theta)
        dec = decCenter + rr*numpy.cos(theta)

    pm_ra = (numpy.random.sample(nsamples)-0.5)*0.1
    pm_dec = (numpy.random.sample(nsamples)-0.5)*0.1
    parallax = numpy.random.sample(nsamples)*0.01
    v_rad = numpy.random.sample(nsamples)*1000.0

    return ra, dec, pm_ra, pm_dec, parallax, v_rad

class AstrometryTestStars(myTestStars):
    database = 'AstrometryTestStarDatabase.db'

class AstrometryTestGalaxies(myTestGals):
    database = 'AstrometryTestGalaxyDatabase.db'

class parallaxTestCatalog(InstanceCatalog, AstrometryStars):
    column_outputs = ['raJ2000', 'decJ2000', 'raObserved', 'decObserved',
                      'properMotionRa', 'properMotionDec',
                      'radialVelocity', 'parallax']

    transformations = {'raJ2000':numpy.degrees, 'decJ2000':numpy.degrees,
                       'raObserved':numpy.degrees, 'decObserved':numpy.degrees,
                       'properMotionRa':numpy.degrees, 'properMotionDec':numpy.degrees,
                       'parallax':arcsecFromRadians}

    default_formats = {'f':'%.12f'}

class testCatalog(InstanceCatalog,AstrometryStars,CameraCoords):
    """
    A (somewhat meaningless) instance catalog class that will allow us
    to run the astrometry routines for testing purposes
    """
    catalog_type = 'test_stars'
    column_outputs=['id','raPhoSim','decPhoSim','raObserved','decObserved',
                   'x_focal_nominal', 'y_focal_nominal', 'x_pupil','y_pupil',
                   'chipName', 'xPix', 'yPix','xFocalPlane','yFocalPlane']
    #Needed to do camera coordinate transforms.
    camera = camTestUtils.CameraWrapper().camera
    default_formats = {'f':'%.12f'}

    delimiter = ';' #so that numpy.loadtxt can parse the chipNames which may contain commas
                     #(see testClassMethods)

    default_columns = [('properMotionRa', 0., float),
                       ('properMotionDec', 0., float),
                       ('parallax', 1.2, float),
                       ('radial_velocity', 0., float)]


class testStellarCatalog(InstanceCatalog, AstrometryStars, CameraCoords):
    """
    Define a catalog of stars with all possible astrometric columns
    """

    camera = camTestUtils.CameraWrapper().camera

    column_outputs = ['glon', 'glat', 'x_focal_nominal', 'y_focal_nominal',
                      'x_pupil', 'y_pupil', 'xPix', 'yPix', 'xFocalPlane', 'yFocalPlane',
                      'chipName', 'raPhoSim', 'decPhoSim', 'raObserved', 'decObserved']

class testGalaxyCatalog(InstanceCatalog, AstrometryGalaxies, CameraCoords):
    """
    Define a catalog of galaxies with all possible astrometric columns
    """

    camera = camTestUtils.CameraWrapper().camera

    column_outputs = ['glon', 'glat', 'x_focal_nominal', 'y_focal_nominal',
                      'x_pupil', 'y_pupil', 'xPix', 'yPix', 'xFocalPlane', 'yFocalPlane',
                      'chipName', 'raPhoSim', 'decPhoSim', 'raObserved', 'decObserved']

class astrometryUnitTest(unittest.TestCase):
    """
    The bulk of this unit test involves inputting a set list of input values
    and comparing the astrometric results to results derived from SLALIB run
    with the same input values.  We have to create a test catalog artificially (rather than
    querying the database) because SLALIB was originally run on values that did not correspond
    to any particular Opsim run.
    """

    @classmethod
    def setUpClass(cls):
        # Create test databases
        cls.starDBName = 'AstrometryTestStarDatabase.db'
        cls.galDBName = 'AstrometryTestGalaxyDatabase.db'
        if os.path.exists(cls.starDBName):
            os.unlink(cls.starDBName)
        makeStarTestDB(filename=cls.starDBName,
                      size=100000, seedVal=1, ramin=199.98*math.pi/180., dra=0.04*math.pi/180.)

        if os.path.exists(cls.galDBName):
            os.unlink(cls.galDBName)
        makeGalTestDB(filename=cls.galDBName,
                      size=100000, seedVal=1, ramin=199.98*math.pi/180., dra=0.04*math.pi/180.)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.starDBName):
            os.unlink(cls.starDBName)

        if os.path.exists(cls.galDBName):
            os.unlink(cls.galDBName)

    def setUp(self):
        self.starDBObject = AstrometryTestStars()
        self.galaxyDBObject = AstrometryTestGalaxies()
        self.metadata={}

        #below are metadata values that need to be set in order for
        #get_getFocalPlaneCoordinates to work.  If we had been querying the database,
        #these would be set to meaningful values.  Because we are generating
        #an artificial set of inputs that must comport to the baseline SLALIB
        #inputs, these are set arbitrarily by hand
        self.metadata['Unrefracted_RA'] = (numpy.radians(200.0), float)
        self.metadata['Unrefracted_Dec'] = (numpy.radians(-30.0), float)
        self.metadata['Opsim_rotskypos'] = (1.0, float)

        self.obs_metadata=ObservationMetaData(mjd=50984.371741,
                                     boundType='circle',
                                     boundLength=0.05,
                                     phoSimMetaData=self.metadata)

        self.cat = testCatalog(self.starDBObject, obs_metadata=self.obs_metadata)
        self.tol=1.0e-5

    @classmethod
    def tearDownClass(cls):
        if os.path.exists('AstrometryTestDatabase.db'):
            os.unlink('AstrometryTestDatabase.db')

    def tearDown(self):
        del self.starDBObject
        del self.galaxyDBObject
        del self.cat
        del self.obs_metadata
        del self.metadata
        del self.tol

    def isNanOrNone(self, value):
        """
        Returns True if value is None or nan.  False otherwise.
        """

        if value is None:
           return True

        try:
            if numpy.isnan(value):
                return True
        except TypeError:
            pass

        return False


    def testWritingOfStars(self):
        """
        Try writing a catalog with all possible Astrometric columns
        """
        stars = testStellarCatalog(self.starDBObject, obs_metadata=self.obs_metadata)
        stars.write_catalog("starsTestOutput.txt")
        os.unlink("starsTestOutput.txt")

    def testWritingOfGalaxies(self):
        """
        Try writing a catalog with all possible Astrometric columns
        """
        galaxies = testGalaxyCatalog(self.galaxyDBObject, obs_metadata=self.obs_metadata)
        galaxies.write_catalog("galTestOutput.txt")
        os.unlink("galTestOutput.txt")


    def testAstrometryExceptions(self):
        """
        Test to make sure that stand-alone astrometry methods raise an exception when they are called without
        the necessary arguments
        """
        obs_metadata = makeObservationMetaData()
        ra, dec, pm_ra, pm_dec, parallax, v_rad = makeRandomSample()
        myAstrometry = AstrometryBase()

        raShort = numpy.array([1.0])
        decShort = numpy.array([1.0])


        ##########test refractionCoefficients
        self.assertRaises(RuntimeError, refractionCoefficients)
        site = obs_metadata.site
        x, y = refractionCoefficients(site=site)

        ##########test applyRefraction
        zd = 0.1
        rzd = applyRefraction(zd, x, y)

        zd = [0.1, 0.2]
        self.assertRaises(RuntimeError, applyRefraction, zd, x, y)

        zd = numpy.array([0.1, 0.2])
        rzd = applyRefraction(zd, x, y)

        ##########test applyPrecession
        #test without mjd
        self.assertRaises(RuntimeError, applyPrecession, ra, dec)

        #test mismatches
        self.assertRaises(RuntimeError, applyPrecession, raShort, dec, mjd=52000.0)
        self.assertRaises(RuntimeError, applyPrecession, ra, decShort, mjd=52000.0)

        #test that it runs
        applyPrecession(ra, dec, mjd=52000.0)

        ##########test applyProperMotion
        raList = list(ra)
        decList = list(dec)
        pm_raList = list(pm_ra)
        pm_decList = list(pm_dec)
        parallaxList = list(parallax)
        v_radList = list(v_rad)

        pm_raShort = numpy.array([pm_ra[0]])
        pm_decShort = numpy.array([pm_dec[0]])
        parallaxShort = numpy.array([parallax[0]])
        v_radShort = numpy.array([v_rad[0]])

        #test without mjd
        self.assertRaises(RuntimeError, applyProperMotion,
                          ra, dec, pm_ra, pm_dec, parallax, v_rad)

        #test passing lists
        self.assertRaises(RuntimeError, applyProperMotion,
                          raList, dec, pm_ra, pm_dec, parallax, v_rad,
                          mjd=52000.0)
        self.assertRaises(RuntimeError, applyProperMotion,
                          ra, decList, pm_ra, pm_dec, parallax, v_rad,
                          mjd=52000.0)
        self.assertRaises(RuntimeError, applyProperMotion,
                          ra, dec, pm_raList, pm_dec, parallax, v_rad,
                          mjd=52000.0)
        self.assertRaises(RuntimeError, applyProperMotion,
                          ra, dec, pm_ra, pm_decList, parallax, v_rad,
                          mjd=52000.0)
        self.assertRaises(RuntimeError, applyProperMotion,
                          ra, dec, pm_ra, pm_dec, parallaxList, v_rad,
                          mjd=52000.0)
        self.assertRaises(RuntimeError, applyProperMotion,
                          ra, dec, pm_ra, pm_dec, parallax, v_radList,
                          mjd=52000.0)

        #test mismatches
        self.assertRaises(RuntimeError, applyProperMotion,
                          raShort, dec, pm_ra, pm_dec, parallax, v_rad,
                          mjd=52000.0)
        self.assertRaises(RuntimeError, applyProperMotion,
                          ra, decShort, pm_ra, pm_dec, parallax, v_rad,
                          mjd=52000.0)
        self.assertRaises(RuntimeError, applyProperMotion,
                          ra, dec, pm_raShort, pm_dec, parallax, v_rad,
                          mjd=52000.0)
        self.assertRaises(RuntimeError, applyProperMotion,
                          ra, dec, pm_ra, pm_decShort, parallax, v_rad,
                          mjd=52000.0)
        self.assertRaises(RuntimeError, applyProperMotion,
                          ra, dec, pm_ra, pm_dec, parallaxShort, v_rad,
                          mjd=52000.0)
        self.assertRaises(RuntimeError, applyProperMotion,
                          ra, dec, pm_ra, pm_dec, parallax, v_radShort,
                          mjd=52000.0)

        #test that it actually runs
        applyProperMotion(ra, dec, pm_ra, pm_dec, parallax, v_rad, mjd=52000.0)
        applyProperMotion(ra[0], dec[0], pm_ra[0], pm_dec[0], parallax[0], v_rad[0],
                          mjd=52000.0)

        ##########test calculateGnomonicProjection
        #test without epoch
        self.assertRaises(RuntimeError, calculateGnomonicProjection, ra, dec, obs_metadata=obs_metadata)

        #test without obs_metadata
        self.assertRaises(RuntimeError, calculateGnomonicProjection, ra, dec, epoch=2000.0)

        #test without mjd
        dummy=ObservationMetaData(unrefractedRA=obs_metadata.unrefractedRA,
                                  unrefractedDec=obs_metadata.unrefractedDec,
                                  rotSkyPos=obs_metadata.rotSkyPos)
        self.assertRaises(RuntimeError, calculateGnomonicProjection, ra, dec, epoch=2000.0, obs_metadata=dummy)

        #test without rotSkyPos
        dummy=ObservationMetaData(unrefractedRA=obs_metadata.unrefractedRA,
                                  unrefractedDec=obs_metadata.unrefractedDec,
                                  mjd=obs_metadata.mjd)
        self.assertRaises(RuntimeError, calculateGnomonicProjection, ra, dec, epoch=2000.0, obs_metadata=dummy)

        #test without unrefractedRA
        dummy=ObservationMetaData(unrefractedDec=obs_metadata.unrefractedDec,
                                  mjd=obs_metadata.mjd,
                                  rotSkyPos=obs_metadata.rotSkyPos)
        self.assertRaises(RuntimeError, calculateGnomonicProjection, ra, dec, epoch=2000.0, obs_metadata=dummy)

        #test without unrefractedDec
        dummy=ObservationMetaData(unrefractedRA=obs_metadata.unrefractedRA,
                                  mjd=obs_metadata.mjd,
                                  rotSkyPos=obs_metadata.rotSkyPos)
        self.assertRaises(RuntimeError, calculateGnomonicProjection, ra, dec, epoch=2000.0, obs_metadata=dummy)

        #test that it actually runs
        dummy=ObservationMetaData(unrefractedRA=obs_metadata.unrefractedRA,
                                  unrefractedDec=obs_metadata.unrefractedDec,
                                  mjd=obs_metadata.mjd,
                                  rotSkyPos=obs_metadata.rotSkyPos)

        #test mismatches
        self.assertRaises(RuntimeError, calculateGnomonicProjection, ra, decShort, epoch=2000.0, obs_metadata=dummy)
        self.assertRaises(RuntimeError, calculateGnomonicProjection, raShort, dec, epoch=2000.0, obs_metadata=dummy)

        #test that it actually runs
        xGnomon, yGnomon = calculateGnomonicProjection(numpy.array([numpy.radians(obs_metadata.unrefractedRA)+0.01]),
                                                       numpy.array([numpy.radians(obs_metadata.unrefractedDec)+0.1]),
                                                       epoch=2000.0, obs_metadata=dummy)

        ##########test appGeoFromICRS
        #test without mjd
        self.assertRaises(RuntimeError, appGeoFromICRS, ra, dec)

        #test with mismatched ra, dec
        self.assertRaises(RuntimeError, appGeoFromICRS, ra, decShort, mjd=52000.0)
        self.assertRaises(RuntimeError, appGeoFromICRS, raShort, dec, mjd=52000.0)

        #test that it actually urns
        test=appGeoFromICRS(ra, dec, mjd=obs_metadata.mjd)

        ##########test observedFromAppGeo
        #test without obs_metadata
        self.assertRaises(RuntimeError, observedFromAppGeo, ra, dec)

        #test without site
        dummy=ObservationMetaData(unrefractedRA=obs_metadata.unrefractedRA,
                                  unrefractedDec=obs_metadata.unrefractedDec,
                                  mjd=obs_metadata.mjd,
                                  site=None)
        self.assertRaises(RuntimeError, observedFromAppGeo, ra, dec, obs_metadata=dummy)

        #test without mjd
        dummy=ObservationMetaData(unrefractedRA=obs_metadata.unrefractedRA,
                                  unrefractedDec=obs_metadata.unrefractedDec,
                                  site=Site())
        self.assertRaises(RuntimeError, observedFromAppGeo, ra, dec, obs_metadata=dummy)

        #test mismatches
        dummy=ObservationMetaData(unrefractedRA=obs_metadata.unrefractedRA,
                                  unrefractedDec=obs_metadata.unrefractedDec,
                                  mjd=obs_metadata.mjd,
                                  site=Site())

        self.assertRaises(RuntimeError, observedFromAppGeo, ra, decShort, obs_metadata=dummy)
        self.assertRaises(RuntimeError, observedFromAppGeo, raShort, dec, obs_metadata=dummy)

        #test that it actually runs
        test = observedFromAppGeo(ra, dec, obs_metadata=dummy)

        ##########test observedFromICRS
        #test without epoch
        self.assertRaises(RuntimeError, observedFromICRS, ra, dec, obs_metadata=obs_metadata)

        #test without obs_metadata
        self.assertRaises(RuntimeError, observedFromICRS, ra, dec, epoch=2000.0)

        #test without mjd
        dummy=ObservationMetaData(unrefractedRA=obs_metadata.unrefractedRA,
                                  unrefractedDec=obs_metadata.unrefractedDec,
                                  site=obs_metadata.site)
        self.assertRaises(RuntimeError, observedFromICRS, ra, dec, epoch=2000.0, obs_metadata=dummy)

        #test that it actually runs
        dummy=ObservationMetaData(unrefractedRA=obs_metadata.unrefractedRA,
                                  unrefractedDec=obs_metadata.unrefractedDec,
                                  site=obs_metadata.site,
                                  mjd=obs_metadata.mjd)

        #test mismatches
        self.assertRaises(RuntimeError, observedFromICRS, ra, decShort, epoch=2000.0, obs_metadata=dummy)
        self.assertRaises(RuntimeError, observedFromICRS, raShort, dec, epoch=2000.0, obs_metadata=dummy)

        #test that it actually runs
        test = observedFromICRS(ra, dec, obs_metadata=dummy, epoch=2000.0)

        ##########test calculatePupilCoordinates
        #test without epoch
        self.assertRaises(RuntimeError, calculatePupilCoordinates, ra, dec,
                          obs_metadata=obs_metadata)

        #test without obs_metadata
        self.assertRaises(RuntimeError, calculatePupilCoordinates, ra, dec,
                          epoch=2000.0)

        #test without unrefractedRA
        dummy = ObservationMetaData(unrefractedDec=obs_metadata.unrefractedDec,
                                    rotSkyPos=obs_metadata.rotSkyPos,
                                    mjd=obs_metadata.mjd)
        self.assertRaises(RuntimeError, calculatePupilCoordinates, ra, dec,
                          epoch=2000.0, obs_metadata=dummy)

        #test without unrefractedDec
        dummy = ObservationMetaData(unrefractedRA=obs_metadata.unrefractedRA,
                                    rotSkyPos=obs_metadata.rotSkyPos,
                                    mjd=obs_metadata.mjd)
        self.assertRaises(RuntimeError, calculatePupilCoordinates, ra, dec,
                          epoch=2000.0, obs_metadata=dummy)

        #test without rotSkyPos
        dummy = ObservationMetaData(unrefractedRA=obs_metadata.unrefractedRA,
                                    unrefractedDec=obs_metadata.unrefractedDec,
                                    mjd=obs_metadata.mjd)
        self.assertRaises(RuntimeError, calculatePupilCoordinates, ra, dec,
                          epoch=2000.0, obs_metadata=dummy)

        #test without mjd
        dummy = ObservationMetaData(unrefractedRA=obs_metadata.unrefractedRA,
                                    unrefractedDec=obs_metadata.unrefractedDec,
                                    rotSkyPos=obs_metadata.rotSkyPos)
        self.assertRaises(RuntimeError, calculatePupilCoordinates, ra, dec,
                          epoch=2000.0, obs_metadata=dummy)


        #test for mismatches
        dummy = ObservationMetaData(unrefractedRA=obs_metadata.unrefractedRA,
                                    unrefractedDec=obs_metadata.unrefractedDec,
                                    rotSkyPos=obs_metadata.rotSkyPos,
                                    mjd=obs_metadata.mjd)

        self.assertRaises(RuntimeError, calculatePupilCoordinates, ra, decShort, epoch=2000.0,
                          obs_metadata=dummy)

        self.assertRaises(RuntimeError, calculatePupilCoordinates, raShort, dec, epoch=2000.0,
                          obs_metadata=dummy)

        #test that it actually runs
        test = calculatePupilCoordinates(ra, dec, obs_metadata=dummy, epoch=2000.0)

    def testCameraCoordsExceptions(self):
        """
        Test to make sure that focal plane methods raise exceptions when coordinates are improperly
        specified.
        """

        #these are just values shown heuristically to give an actual chip name
        ra = numpy.array(numpy.radians(self.obs_metadata.unrefractedRA) - numpy.array([1.01, 1.02])*numpy.radians(1.0/3600.0))
        dec = numpy.array(numpy.radians(self.obs_metadata.unrefractedDec) - numpy.array([2.02, 2.01])*numpy.radians(1.0/3600.0))

        ra, dec = observedFromICRS(ra, dec, obs_metadata=self.obs_metadata, epoch=self.starDBObject.epoch)

        xPupil = numpy.array([-0.000262243770, -0.00000234])
        yPupil = numpy.array([0.000199467792, 0.000189334])

        ##########test findChipName

        name = findChipName(ra=ra, dec=dec,
                            epoch=self.cat.db_obj.epoch,
                            obs_metadata=self.cat.obs_metadata,
                            camera=self.cat.camera)

        self.assertTrue(name[0] is not None)

        name = findChipName(xPupil=xPupil, yPupil=yPupil,
                            camera=self.cat.camera)

        self.assertTrue(name[0] is not None)

        #test when specifying no coordinates
        self.assertRaises(RuntimeError, findChipName)

        #test when specifying both sets fo coordinates
        self.assertRaises(RuntimeError, findChipName, xPupil=xPupil, yPupil=yPupil,
                  ra=ra, dec=dec, camera=self.cat.camera)

        #test when failing to specify camera
        self.assertRaises(RuntimeError, findChipName, ra=ra, dec=dec,
                          obs_metadata=self.obs_metadata, epoch=2000.0)
        self.assertRaises(RuntimeError, findChipName, xPupil=xPupil, yPupil=yPupil)

        #test when failing to specify obs_metadata
        self.assertRaises(RuntimeError, findChipName, ra=ra, dec=dec, epoch=2000.0,
                          camera=self.cat.camera)

        #test when failing to specify epoch
        self.assertRaises(RuntimeError, findChipName, ra=ra, dec=dec, camera=self.cat.camera,
                          obs_metadata=self.obs_metadata)

        #test mismatches
        self.assertRaises(RuntimeError, findChipName, ra=numpy.array([ra[0]]), dec=dec,
                            epoch=self.cat.db_obj.epoch,
                            obs_metadata=self.cat.obs_metadata,
                            camera=self.cat.camera)

        self.assertRaises(RuntimeError, findChipName, ra=ra, dec=numpy.array([dec[0]]),
                            epoch=self.cat.db_obj.epoch,
                            obs_metadata=self.cat.obs_metadata,
                            camera=self.cat.camera)

        self.assertRaises(RuntimeError, findChipName, xPupil=numpy.array([xPupil[0]]), yPupil=yPupil,
                                        camera=self.cat.camera)
        self.assertRaises(RuntimeError, findChipName, xPupil=xPupil, yPupil=numpy.array([yPupil[0]]),
                                        camera=self.cat.camera)

        #test lists
        self.assertRaises(RuntimeError, findChipName, ra=list(ra), dec=dec,
                            epoch=self.cat.db_obj.epoch,
                            obs_metadata=self.cat.obs_metadata,
                            camera=self.cat.camera)

        self.assertRaises(RuntimeError, findChipName, ra=ra, dec=list(dec),
                            epoch=self.cat.db_obj.epoch,
                            obs_metadata=self.cat.obs_metadata,
                            camera=self.cat.camera)

        self.assertRaises(RuntimeError, findChipName, xPupil=list(xPupil), yPupil=yPupil,
                                        camera=self.cat.camera)
        self.assertRaises(RuntimeError, findChipName, xPupil=xPupil, yPupil=list(yPupil),
                                        camera=self.cat.camera)


        ##########test FocalPlaneCoordinates

        #test that it actually runs
        xx, yy = calculateFocalPlaneCoordinates(xPupil=xPupil, yPupil=yPupil, camera=self.cat.camera)
        xx, yy = calculateFocalPlaneCoordinates(ra=ra, dec=dec,
                                                epoch=self.cat.db_obj.epoch, obs_metadata=self.cat.obs_metadata,
                                                camera=self.cat.camera)

        #test without any coordinates
        self.assertRaises(RuntimeError, calculateFocalPlaneCoordinates, camera=self.cat.camera)

        #test specifying both ra,dec and xPupil,yPupil
        self.assertRaises(RuntimeError, calculateFocalPlaneCoordinates, ra=ra, dec=dec,
                             xPupil=xPupil, yPupil=yPupil, camera=self.cat.camera)

        #test without camera
        self.assertRaises(RuntimeError, calculateFocalPlaneCoordinates, xPupil=xPupil, yPupil=yPupil)
        self.assertRaises(RuntimeError, calculateFocalPlaneCoordinates, ra=ra, dec=dec,
                                        epoch=self.cat.db_obj.epoch, obs_metadata=self.cat.obs_metadata)

        #test without epoch
        self.assertRaises(RuntimeError, calculateFocalPlaneCoordinates, ra=ra, dec=dec,
                                                obs_metadata=self.cat.obs_metadata,
                                                camera=self.cat.camera)

        #test without obs_metadata
        self.assertRaises(RuntimeError, calculateFocalPlaneCoordinates, ra=ra, dec=dec,
                                                epoch=self.cat.db_obj.epoch,
                                                camera=self.cat.camera)

        #test with lists
        self.assertRaises(RuntimeError, calculateFocalPlaneCoordinates, xPupil=list(xPupil), yPupil=yPupil,
                          camera=self.cat.camera)
        self.assertRaises(RuntimeError, calculateFocalPlaneCoordinates, xPupil=xPupil, yPupil=list(yPupil),
                          camera=self.cat.camera)

        self.assertRaises(RuntimeError, calculateFocalPlaneCoordinates, ra=list(ra), dec=dec,
                                        epoch=self.cat.db_obj.epoch, camera=self.cat.camera)
        self.assertRaises(RuntimeError, calculateFocalPlaneCoordinates, ra=ra, dec=list(dec),
                                        epoch=self.cat.db_obj.epoch,
                                        obs_metadata=self.cat.obs_metadata,
                                        camera=self.cat.camera)

        #test mismatches
        self.assertRaises(RuntimeError, calculateFocalPlaneCoordinates, xPupil=numpy.array([xPupil[0]]), yPupil=yPupil,
                          camera=self.cat.camera)
        self.assertRaises(RuntimeError, calculateFocalPlaneCoordinates, xPupil=xPupil, yPupil=numpy.array([yPupil[0]]),
                          camera=self.cat.camera)

        self.assertRaises(RuntimeError, calculateFocalPlaneCoordinates, ra=numpy.array([ra[0]]), dec=dec,
                                        epoch=self.cat.db_obj.epoch, camera=self.cat.camera)
        self.assertRaises(RuntimeError, calculateFocalPlaneCoordinates, ra=ra, dec=numpy.array([dec[0]]),
                                        epoch=self.cat.db_obj.epoch,
                                        obs_metadata=self.cat.obs_metadata,
                                        camera=self.cat.camera)


        ##########test calculatePixelCoordinates
         #test that it actually runs
        xx, yy = calculatePixelCoordinates(xPupil=xPupil, yPupil=yPupil, camera=self.cat.camera)
        xx, yy = calculatePixelCoordinates(ra=ra, dec=dec,
                                                epoch=self.cat.db_obj.epoch, obs_metadata=self.cat.obs_metadata,
                                                camera=self.cat.camera)

        #test without any coordinates
        self.assertRaises(RuntimeError, calculatePixelCoordinates, camera=self.cat.camera)

        #test specifying both ra,dec and xPupil,yPupil
        self.assertRaises(RuntimeError, calculatePixelCoordinates, ra=ra, dec=dec,
                             xPupil=xPupil, yPupil=yPupil, camera=self.cat.camera)

        #test without camera
        self.assertRaises(RuntimeError, calculatePixelCoordinates, xPupil=xPupil, yPupil=yPupil)
        self.assertRaises(RuntimeError, calculatePixelCoordinates, ra=ra, dec=dec,
                                        epoch=self.cat.db_obj.epoch, obs_metadata=self.cat.obs_metadata)

        #test without epoch
        self.assertRaises(RuntimeError, calculatePixelCoordinates, ra=ra, dec=dec,
                                                obs_metadata=self.cat.obs_metadata,
                                                camera=self.cat.camera)

        #test without obs_metadata
        self.assertRaises(RuntimeError, calculatePixelCoordinates, ra=ra, dec=dec,
                                                epoch=self.cat.db_obj.epoch,
                                                camera=self.cat.camera)

        #test with lists
        self.assertRaises(RuntimeError, calculatePixelCoordinates, xPupil=list(xPupil), yPupil=yPupil,
                          camera=self.cat.camera)
        self.assertRaises(RuntimeError, calculatePixelCoordinates, xPupil=xPupil, yPupil=list(yPupil),
                          camera=self.cat.camera)

        self.assertRaises(RuntimeError, calculatePixelCoordinates, ra=list(ra), dec=dec,
                                        epoch=self.cat.db_obj.epoch, camera=self.cat.camera)
        self.assertRaises(RuntimeError, calculatePixelCoordinates, ra=ra, dec=list(dec),
                                        epoch=self.cat.db_obj.epoch,
                                        obs_metadata=self.cat.obs_metadata,
                                        camera=self.cat.camera)

        #test mismatches
        self.assertRaises(RuntimeError, calculatePixelCoordinates, xPupil=numpy.array([xPupil[0]]), yPupil=yPupil,
                          camera=self.cat.camera)
        self.assertRaises(RuntimeError, calculatePixelCoordinates, xPupil=xPupil, yPupil=numpy.array([yPupil[0]]),
                          camera=self.cat.camera)

        self.assertRaises(RuntimeError, calculatePixelCoordinates, ra=numpy.array([ra[0]]), dec=dec,
                                        epoch=self.cat.db_obj.epoch, camera=self.cat.camera)
        self.assertRaises(RuntimeError, calculatePixelCoordinates, ra=ra, dec=numpy.array([dec[0]]),
                                        epoch=self.cat.db_obj.epoch,
                                        obs_metadata=self.cat.obs_metadata,
                                        camera=self.cat.camera)

        chipNames = findChipName(xPupil=xPupil, yPupil=yPupil, camera=self.cat.camera)
        calculatePixelCoordinates(xPupil=xPupil, yPupil=yPupil, chipNames=chipNames, camera=self.cat.camera)
        self.assertRaises(RuntimeError, calculatePixelCoordinates, xPupil=xPupil, yPupil=yPupil,
                                        camera=self.cat.camera, chipNames=[chipNames[0]])

        chipNames=findChipName(ra=ra, dec=dec, obs_metadata=self.cat.obs_metadata, epoch=self.cat.db_obj.epoch,
                               camera=self.cat.camera)
        calculatePixelCoordinates(ra=ra, dec=dec, obs_metadata=self.cat.obs_metadata, epoch=self.cat.db_obj.epoch,
                                  camera=self.cat.camera, chipNames=chipNames)
        self.assertRaises(RuntimeError, calculatePixelCoordinates, ra=ra, dec=dec, obs_metadata=self.cat.obs_metadata, epoch=self.cat.db_obj.epoch,
                                  camera=self.cat.camera, chipNames=[chipNames[0]])


    def testUtilityMethods(self):
        """
        Generate a catalog using the methods from AstrometryUtils.py and CameraUtils.py.
        Read that data in, and then recalculate the values 'by hand' to make sure
        that they are consistent.
        """

        self.cat.write_catalog("AstrometryTestCatalog.txt")

        dtype = [('id',int),('raPhoSim',float),('decPhoSim',float),('raObserved',float),
                 ('decObserved',float),('x_focal_nominal',float),('y_focal_nominal',float),
                 ('x_pupil',float),('y_pupil',float),('chipName',str,11),('xPix',float),
                 ('yPix',float),('xFocalPlane',float),('yFocalPlane',float)]

        baselineData = numpy.loadtxt('AstrometryTestCatalog.txt', dtype=dtype, delimiter=';')

        pupilTest = calculatePupilCoordinates(baselineData['raObserved'],
                                              baselineData['decObserved'],
                                              obs_metadata=self.obs_metadata,
                                              epoch=2000.0)

        for (xxtest, yytest, xx, yy) in \
                zip(pupilTest[0], pupilTest[1], baselineData['x_pupil'], baselineData['y_pupil']):
            self.assertAlmostEqual(xxtest,xx,6)
            self.assertAlmostEqual(yytest,yy,6)

        focalTest = calculateFocalPlaneCoordinates(xPupil=pupilTest[0],
                                      yPupil=pupilTest[1], camera=self.cat.camera)

        focalRa = calculateFocalPlaneCoordinates(ra=baselineData['raObserved'],
                        dec=baselineData['decObserved'],
                        epoch=self.cat.db_obj.epoch, obs_metadata=self.cat.obs_metadata,
                        camera=self.cat.camera)

        for (xxtest, yytest, xxra, yyra, xx, yy) in \
                zip(focalTest[0], focalTest[1], focalRa[0], focalRa[1],
                        baselineData['xFocalPlane'], baselineData['yFocalPlane']):

            self.assertAlmostEqual(xxtest,xx,6)
            self.assertAlmostEqual(yytest,yy,6)
            self.assertAlmostEqual(xxra,xx,6)
            self.assertAlmostEqual(yyra,yy,6)

        pixTest = calculatePixelCoordinates(xPupil=pupilTest[0], yPupil=pupilTest[1],
                                            camera=self.cat.camera)
        pixTestRaDec = calculatePixelCoordinates(ra=baselineData['raObserved'],
                                   dec=baselineData['decObserved'],
                                   epoch=self.cat.db_obj.epoch,
                                   obs_metadata=self.cat.obs_metadata,
                                   camera=self.cat.camera)

        for (xxtest, yytest, xxra, yyra, xx, yy) in \
                zip(pixTest[0], pixTest[1], pixTestRaDec[0], pixTestRaDec[1],
                           baselineData['xPix'], baselineData['yPix']):

            if not numpy.isnan(xx) and not numpy.isnan(yy):
                self.assertAlmostEqual(xxtest,xx,5)
                self.assertAlmostEqual(yytest,yy,5)
                self.assertAlmostEqual(xxra,xx,5)
                self.assertAlmostEqual(yyra,yy,5)
            else:
                self.assertTrue(numpy.isnan(xx))
                self.assertTrue(numpy.isnan(yy))
                self.assertTrue(numpy.isnan(xxra))
                self.assertTrue(numpy.isnan(yyra))
                self.assertTrue(numpy.isnan(xxtest))
                self.assertTrue(numpy.isnan(yytest))

        gnomonTest = calculateGnomonicProjection(baselineData['raObserved'],
                             baselineData['decObserved'], obs_metadata=self.obs_metadata,
                             epoch=2000.0)
        for (xxtest, yytest, xx, yy) in \
                zip(gnomonTest[0], gnomonTest[1],
                    baselineData['x_focal_nominal'], baselineData['y_focal_nominal']):

            self.assertAlmostEqual(xxtest,xx,6)
            self.assertAlmostEqual(yytest,yy,6)

        nameTest = findChipName(xPupil=pupilTest[0], yPupil=pupilTest[1],
                                epoch=self.cat.db_obj.epoch,
                                obs_metadata=self.cat.obs_metadata,
                                camera=self.cat.camera)
        nameRA = findChipName(ra=baselineData['raObserved'], dec=baselineData['decObserved'],
                              epoch=self.cat.db_obj.epoch, obs_metadata=self.cat.obs_metadata,
                              camera=self.cat.camera)

        for (ntest, nra, ncontrol) in zip(nameTest, nameRA, baselineData['chipName']):
            if ncontrol != 'None':
                self.assertEqual(ntest,ncontrol)
                self.assertEqual(nra,ncontrol)
            else:
                self.assertTrue(ntest is None)
                self.assertTrue(nra is None)

        if os.path.exists("AstrometryTestCatalog.txt"):
            os.unlink("AstrometryTestCatalog.txt")


    def testApplyPrecession(self):

        ra=numpy.zeros((3),dtype=float)
        dec=numpy.zeros((3),dtype=float)

        ra[0]=2.549091039839124218e+00
        dec[0]=5.198752733024248895e-01
        ra[1]=8.693375673649429425e-01
        dec[1]=1.038086165642298164e+00
        ra[2]=7.740864769302191473e-01
        dec[2]=2.758053025017753179e-01

        self.assertRaises(RuntimeError, applyPrecession, ra, dec)

        #The mjd kwarg in applyPrecession below is a hold-over from
        #a misunderstanding in the API for the pal.prenut() back
        #when we generated the test data.  We passed a julian epoch
        #(in years) when PAL actually wanted an mjd.  The underlying
        #code has been fixed.  This test still passes a julian
        #epoch so that it will give the same results as the control
        #SLALIB run.
        output=applyPrecession(ra,dec, mjd=pal.epj(2000.0))

        self.assertAlmostEqual(output[0][0],2.514361575034799401e+00,6)
        self.assertAlmostEqual(output[1][0], 5.306722463159389003e-01,6)
        self.assertAlmostEqual(output[0][1],8.224493314855578774e-01,6)
        self.assertAlmostEqual(output[1][1],1.029318353760459104e+00,6)
        self.assertAlmostEqual(output[0][2],7.412362765815005972e-01,6)
        self.assertAlmostEqual(output[1][2],2.662034339930458571e-01,6)

    def testApplyProperMotion(self):

        ra=numpy.zeros((3),dtype=float)
        dec=numpy.zeros((3),dtype=float)
        pm_ra=numpy.zeros((3),dtype=float)
        pm_dec=numpy.zeros((3),dtype=float)
        parallax=numpy.zeros((3),dtype=float)
        v_rad=numpy.zeros((3),dtype=float)

        ra[0]=2.549091039839124218e+00
        dec[0]=5.198752733024248895e-01
        pm_ra[0]=-8.472633255615005918e-05
        pm_dec[0]=-5.618517146980475171e-07
        parallax[0]=9.328946209650547383e-02
        v_rad[0]=3.060308412186171267e+02

        ra[1]=8.693375673649429425e-01
        dec[1]=1.038086165642298164e+00
        pm_ra[1]=-5.848962163813087908e-05
        pm_dec[1]=-3.000346282603337522e-05
        parallax[1]=5.392364722571952457e-02
        v_rad[1]=4.785834687356999098e+02

        ra[2]=7.740864769302191473e-01
        dec[2]=2.758053025017753179e-01
        pm_ra[2]=5.904070507320858615e-07
        pm_dec[2]=-2.958381482198743105e-05
        parallax[2]=2.172865273161764255e-02
        v_rad[2]=-3.225459751425886452e+02

        ep=2.001040286039033845e+03

        #The proper motion arguments in this function are weird
        #because there was a misunderstanding when the baseline
        #SLALIB data was made.
        output=applyProperMotion(ra,dec,pm_ra*numpy.cos(dec),pm_dec/numpy.cos(dec),
                                 radiansFromArcsec(parallax),v_rad,epoch=ep,
                                 mjd=self.obs_metadata.mjd)

        self.assertAlmostEqual(output[0][0],2.549309127917495754e+00,6)
        self.assertAlmostEqual(output[1][0],5.198769294314042888e-01,6)
        self.assertAlmostEqual(output[0][1],8.694881589882680339e-01,6)
        self.assertAlmostEqual(output[1][1],1.038238225568303363e+00,6)
        self.assertAlmostEqual(output[0][2],7.740849573146946216e-01,6)
        self.assertAlmostEqual(output[1][2],2.758844356561930278e-01,6)


    def testAppGeoFromICRS(self):
        ra=numpy.zeros((3),dtype=float)
        dec=numpy.zeros((3),dtype=float)
        pm_ra=numpy.zeros((3),dtype=float)
        pm_dec=numpy.zeros((3),dtype=float)
        parallax=numpy.zeros((3),dtype=float)
        v_rad=numpy.zeros((3),dtype=float)


        ra[0]=2.549091039839124218e+00
        dec[0]=5.198752733024248895e-01
        pm_ra[0]=-8.472633255615005918e-05
        pm_dec[0]=-5.618517146980475171e-07
        parallax[0]=9.328946209650547383e-02
        v_rad[0]=3.060308412186171267e+02

        ra[1]=8.693375673649429425e-01
        dec[1]=1.038086165642298164e+00
        pm_ra[1]=-5.848962163813087908e-05
        pm_dec[1]=-3.000346282603337522e-05
        parallax[1]=5.392364722571952457e-02
        v_rad[1]=4.785834687356999098e+02

        ra[2]=7.740864769302191473e-01
        dec[2]=2.758053025017753179e-01
        pm_ra[2]=5.904070507320858615e-07
        pm_dec[2]=-2.958381482198743105e-05
        parallax[2]=2.172865273161764255e-02
        v_rad[2]=-3.225459751425886452e+02

        ep=2.001040286039033845e+03
        mjd=2.018749109074271473e+03

        #The proper motion arguments in this function are weird
        #because there was a misunderstanding when the baseline
        #SLALIB data was made.
        output=appGeoFromICRS(ra,dec,pm_ra=pm_ra*numpy.cos(dec), pm_dec=pm_dec/numpy.cos(dec),
                              parallax=radiansFromArcsec(parallax),v_rad=v_rad, epoch=ep,
                              mjd=mjd)

        self.assertAlmostEqual(output[0][0],2.525858337335585180e+00,6)
        self.assertAlmostEqual(output[1][0],5.309044018653210628e-01,6)
        self.assertAlmostEqual(output[0][1],8.297492370691380570e-01,6)
        self.assertAlmostEqual(output[1][1],1.037400063009288331e+00,6)
        self.assertAlmostEqual(output[0][2],7.408639821342507537e-01,6)
        self.assertAlmostEqual(output[1][2],2.703229189890907214e-01,6)

    def testObservedFromAppGeo(self):
        """
        Note: this routine depends on Aopqk which fails if zenith distance
        is too great (or, at least, it won't warn you if the zenith distance
        is greater than pi/2, in which case answers won't make sense)
        """

        ra=numpy.zeros((3),dtype=float)
        dec=numpy.zeros((3),dtype=float)

        #we need to pass wv as the effective wavelength for methods that
        #calculate refraction because, when the control SLALIB runs were
        #done we misinterpreted the units of wavelength to be Angstroms
        #rather than microns.
        wv = 5000.0

        ra[0]=2.549091039839124218e+00
        dec[0]=5.198752733024248895e-01
        ra[1]=4.346687836824714712e-01
        dec[1]=-5.190430828211490821e-01
        ra[2]=7.740864769302191473e-01
        dec[2]=2.758053025017753179e-01

        mjd=2.018749109074271473e+03
        obs_metadata=ObservationMetaData(mjd=mjd,
                                     boundType='circle',
                                     boundLength=0.05,
                                     phoSimMetaData=self.metadata)

        output=observedFromAppGeo(ra,dec, wavelength=wv, obs_metadata=obs_metadata)

        self.assertAlmostEqual(output[0][0],2.547475965605183745e+00,6)
        self.assertAlmostEqual(output[1][0],5.187045152602967057e-01,6)

        self.assertAlmostEqual(output[0][1],4.349858626308809040e-01,6)
        self.assertAlmostEqual(output[1][1],-5.191213875880701378e-01,6)

        self.assertAlmostEqual(output[0][2],7.743528611421227614e-01,6)
        self.assertAlmostEqual(output[1][2],2.755070101670137328e-01,6)

        output=observedFromAppGeo(ra,dec,altAzHr=True, wavelength=wv, obs_metadata=obs_metadata)

        self.assertAlmostEqual(output[0][0],2.547475965605183745e+00,6)
        self.assertAlmostEqual(output[1][0],5.187045152602967057e-01,6)
        self.assertAlmostEqual(output[2][0],1.168920017932007643e-01,6)
        self.assertAlmostEqual(output[3][0],8.745379535264000692e-01,6)

        self.assertAlmostEqual(output[0][1],4.349858626308809040e-01,6)
        self.assertAlmostEqual(output[1][1],-5.191213875880701378e-01,6)
        self.assertAlmostEqual(output[2][1],6.766119585479937193e-01,6)
        self.assertAlmostEqual(output[3][1],4.433969998336554141e+00,6)

        self.assertAlmostEqual(output[0][2],7.743528611421227614e-01,6)
        self.assertAlmostEqual(output[1][2],2.755070101670137328e-01,6)
        self.assertAlmostEqual(output[2][2],5.275840601437552513e-01,6)
        self.assertAlmostEqual(output[3][2],5.479759580847959555e+00,6)

        output=observedFromAppGeo(ra,dec,includeRefraction=False,
                                  wavelength=wv, obs_metadata=obs_metadata)

        self.assertAlmostEqual(output[0][0],2.549091783674975353e+00,6)
        self.assertAlmostEqual(output[1][0],5.198746844679964507e-01,6)

        self.assertAlmostEqual(output[0][1],4.346695674418772359e-01,6)
        self.assertAlmostEqual(output[1][1],-5.190436610150490626e-01,6)

        self.assertAlmostEqual(output[0][2],7.740875471580924705e-01,6)
        self.assertAlmostEqual(output[1][2],2.758055401087299296e-01,6)

        output=observedFromAppGeo(ra,dec,includeRefraction=False,
                                  altAzHr=True, wavelength=wv, obs_metadata=obs_metadata)

        self.assertAlmostEqual(output[0][0],2.549091783674975353e+00,6)
        self.assertAlmostEqual(output[1][0],5.198746844679964507e-01,6)
        self.assertAlmostEqual(output[2][0],1.150652107618796299e-01,6)
        self.assertAlmostEqual(output[3][0],8.745379535264000692e-01,6)

        self.assertAlmostEqual(output[0][1],4.346695674418772359e-01,6)
        self.assertAlmostEqual(output[1][1],-5.190436610150490626e-01,6)
        self.assertAlmostEqual(output[2][1],6.763265401447272618e-01,6)
        self.assertAlmostEqual(output[3][1],4.433969998336554141e+00,6)

        self.assertAlmostEqual(output[0][2],7.740875471580924705e-01,6)
        self.assertAlmostEqual(output[1][2],2.758055401087299296e-01,6)
        self.assertAlmostEqual(output[2][2],5.271912536356709866e-01,6)
        self.assertAlmostEqual(output[3][2],5.479759580847959555e+00,6)

    def testMeanObservedPlace_NoRefraction(self):

        ra=numpy.zeros((3),dtype=float)
        dec=numpy.zeros((3),dtype=float)

        ra[0]=2.549091039839124218e+00
        dec[0]=5.198752733024248895e-01
        ra[1]=4.346687836824714712e-01
        dec[1]=-5.190430828211490821e-01
        ra[2]=7.740864769302191473e-01
        dec[2]=2.758053025017753179e-01

        mjd=2.018749109074271473e+03
        obs_metadata=ObservationMetaData(mjd=mjd,
                                     boundType='circle',
                                     boundLength=0.05,
                                     phoSimMetaData=self.metadata)

        output=observedFromAppGeo(ra,dec,altAzHr=True,
                                  includeRefraction=False, obs_metadata=obs_metadata)

        self.assertAlmostEqual(output[0][0],2.549091783674975353e+00,6)
        self.assertAlmostEqual(output[1][0],5.198746844679964507e-01,6)
        self.assertAlmostEqual(output[0][1],4.346695674418772359e-01,6)
        self.assertAlmostEqual(output[1][1],-5.190436610150490626e-01,6)
        self.assertAlmostEqual(output[0][2],7.740875471580924705e-01,6)
        self.assertAlmostEqual(output[1][2],2.758055401087299296e-01,6)
        self.assertAlmostEqual(output[2][2],5.271914342095551653e-01,6)
        self.assertAlmostEqual(output[3][2],5.479759402150099490e+00,6)

    def testRefractionCoefficients(self):
        output=refractionCoefficients(wavelength=5000.0, site=self.obs_metadata.site)

        self.assertAlmostEqual(output[0],2.295817926320665320e-04,6)
        self.assertAlmostEqual(output[1],-2.385964632924575670e-07,6)

    def testApplyRefraction(self):
        coeffs=refractionCoefficients(wavelength=5000.0, site=self.obs_metadata.site)

        output=applyRefraction(0.25*numpy.pi,coeffs[0],coeffs[1])

        self.assertAlmostEqual(output,7.851689251070859132e-01,6)


    def testPixelPos(self):
        for chunk, chunkMap in self.cat.iter_catalog_chunks():
            self.assertTrue(numpy.all(numpy.isfinite(self.cat.column_by_name('x_pupil'))))
            self.assertTrue(numpy.all(numpy.isfinite(self.cat.column_by_name('y_pupil'))))
            for x, y, cname in zip(self.cat.column_by_name('xPix'), self.cat.column_by_name('yPix'),
                                   self.cat.column_by_name('chipName')):
                if cname is None:
                    #make sure that x and y are not set if the object doesn't land on a chip
                    self.assertTrue(not numpy.isfinite(x) and not numpy.isfinite(y))
                else:
                    #make sure the pixel positions are inside the detector bounding box.
                    self.assertTrue(afwGeom.Box2D(self.cat.camera[cname].getBBox()).contains(afwGeom.Point2D(x,y)))


    def testParallax(self):
        """
        This test will output a catalog of ICRS and observed positions.
        It will also output the quantities (proper motion, radial velocity,
        and parallax) needed to apply the transformaiton between the two.
        It will then run the catalog through PALPY and verify that the catalog
        generating code correctly applied the transformations.
        """

        #create and write a catalog that performs astrometric transformations
        #on a cartoon star database
        cat = parallaxTestCatalog(self.starDBObject, obs_metadata=self.obs_metadata)
        parallaxName = 'parallaxCatalog.sav'
        cat.write_catalog(parallaxName)

        data = numpy.genfromtxt(parallaxName,delimiter=',')
        epoch = cat.db_obj.epoch
        mjd = cat.obs_metadata.mjd
        prms = pal.mappa(epoch, mjd)
        for vv in data:
            #run the PALPY routines that actuall do astrometry `by hand' and compare
            #the results to the contents of the catalog
            ra0 = numpy.radians(vv[0])
            dec0 = numpy.radians(vv[1])
            pmra = numpy.radians(vv[4])
            pmdec = numpy.radians(vv[5])
            rv = vv[6]
            px = vv[7]
            ra_apparent, dec_apparent = pal.mapqk(ra0, dec0, pmra, pmdec, px, rv, prms)
            ra_apparent = numpy.array([ra_apparent])
            dec_apparent = numpy.array([dec_apparent])
            raObserved, decObserved = observedFromAppGeo(ra_apparent, dec_apparent,
                                                                 obs_metadata=cat.obs_metadata)

            self.assertAlmostEqual(raObserved[0],numpy.radians(vv[2]),7)
            self.assertAlmostEqual(decObserved[0],numpy.radians(vv[3]),7)

        if os.path.exists(parallaxName):
            os.unlink(parallaxName)

def suite():
    utilsTests.init()
    suites = []
    suites += unittest.makeSuite(astrometryUnitTest)
    return unittest.TestSuite(suites)

def run(shouldExit=False):
    utilsTests.run(suite(),shouldExit)

if __name__ == "__main__":
    run(True)
