from enum import Enum
from typing import Dict, List, Union

from cereal import car
from common.numpy_fast import interp
from selfdrive.car import dbc_dict
from selfdrive.car.docs_definitions import CarFootnote, CarInfo, Column

Ecu = car.CarParams.Ecu


class CarControllerParams():
  def __init__(self):
    self.STEER_MAX = 300
    self.STEER_STEP = 2              # how often we update the steer cmd
    # self.STEER_DELTA_UP = 14          # ~1s time to peak torque (255/50hz/1s)
    # self.STEER_DELTA_DOWN = 34       # ~0.4s from peak torque to zero
    self.STEER_DELTA_UP_BP = [10., 20.] # [m/s]
    self.STEER_DELTA_UP_V = [20., 7.] # [steer command]
    self.STEER_DELTA_DOWN_BP = [10., 20.] # [m/s]
    self.STEER_DELTA_DOWN_V = [32., 17.] # [steer command]
    self.MIN_STEER_SPEED = 3.
    self.STEER_DRIVER_ALLOWANCE = 50   # allowed driver torque before start limiting
    self.STEER_DRIVER_MULTIPLIER = 4   # weight driver torque heavily
    self.STEER_DRIVER_FACTOR = 100     # from dbc
    self.NEAR_STOP_BRAKE_PHASE = 0.5  # m/s, more aggressive braking near full stop

    # Takes case of "Service Adaptive Cruise" and "Service Front Camera"
    # dashboard messages.
    self.ADAS_KEEPALIVE_STEP = 100
    self.CAMERA_KEEPALIVE_STEP = 100

    # pedal lookups, only for Volt
    self.MAX_GAS = 4095
    self.ZERO_GAS = 2048
    self.MAX_BRAKE = 350             # Should be around 3.5m/s^2, including regen, at speed, and 2.5 below regen speed, so we'll add in the difference

    self.ACCEL_MAX = 3.0 # m/s^2 (max accel of sport profile in longitudinal_planner.py)

    # Allow small margin below -3.5 m/s^2 from ISO 15622:2018 since we
    # perform the closed loop control, and might need some
    # to apply some more braking if we're on a downhill slope.
    # Our controller should still keep the 2 second average above
    # -3.5 m/s^2 as per planner limits
    self.ACCEL_MIN = -3.5 # m/s^2

    self.MAX_ACC_REGEN = 1404  # ACC Regen braking is slightly less powerful than max regen paddle
    self.GAS_LOOKUP_BP = [-1.1, 0., self.ACCEL_MAX]
    self.GAS_LOOKUP_V = [self.MAX_ACC_REGEN, self.ZERO_GAS, self.MAX_GAS]
    self.BRAKE_LOOKUP_BP = [self.ACCEL_MIN, -1.1]
    self.BRAKE_LOOKUP_V = [self.MAX_BRAKE, 0]
    
    self.v_ego = 100.
    self.future_curvature = 0.
    self.MIN_STEER_DELTA_UP = min(self.STEER_DELTA_UP_V)
    self.MIN_STEER_DELTA_DOWN = min(self.STEER_DELTA_DOWN_V)
    self.CURVATURE_STEER_DELTA_FACTOR_BP = [0.001, 0.015] # [rad/meter]
    self.CURVATURE_STEER_DELTA_FACTOR_V = [0., 1.] # factor of higher torque rate limit used. when it's 1, the higher limit is used, or the stock value when 0

  @property
  def STEER_DELTA_UP(self):
    limit = interp(self.v_ego, self.STEER_DELTA_UP_BP, self.STEER_DELTA_UP_V)
    k = interp(self.future_curvature, self.CURVATURE_STEER_DELTA_FACTOR_BP, self.CURVATURE_STEER_DELTA_FACTOR_V)
    return int(round(k * limit + (1 - k) * self.MIN_STEER_DELTA_UP))
  
  @property
  def STEER_DELTA_DOWN(self):
    limit = interp(self.v_ego, self.STEER_DELTA_DOWN_BP, self.STEER_DELTA_DOWN_V)
    k = interp(self.future_curvature, self.CURVATURE_STEER_DELTA_FACTOR_BP, self.CURVATURE_STEER_DELTA_FACTOR_V)
    return int(round(k * limit + (1 - k) * self.MIN_STEER_DELTA_DOWN))
    
    # determined by letting Volt regen to a stop in L gear from 75mph
  EV_GAS_BRAKE_THRESHOLD_BP = [1.2, 1.29, 1.52, 1.55, 1.6, 1.7, 1.8, 2.0, 2.2, 2.5, 5.52, 9.6, 20.5, 23.5, 35.0] # [m/s]
  EV_GAS_BRAKE_THRESHOLD_V = [0.13, 0.0, -0.14, -0.16, -0.18, -0.215, -0.255, -0.32, -0.41, -0.5, -0.72, -0.895, -1.125, -1.145, -1.16] # [m/s^s]
  EV_GAS_BRAKE_THRESHOLD_ICE_V = [i/2 for i in [0.13, 0.0, -0.14, -0.16, -0.18, -0.215, -0.255, -0.32, -0.41, -0.5, -0.72, -0.895, -1.125, -1.145, -1.16]] # [m/s^s] less volt regen braking is available when ice is on
  EV_GAS_BRAKE_THRESHOLD_MIN_V = min(EV_GAS_BRAKE_THRESHOLD_V)
  
  def update_gas_brake_threshold(self, v_ego, ice_on):
    gas_brake_threshold = interp(v_ego, self.EV_GAS_BRAKE_THRESHOLD_BP, self.EV_GAS_BRAKE_THRESHOLD_ICE_V if ice_on else self.EV_GAS_BRAKE_THRESHOLD_V)
    max_brake = int(self.MAX_BRAKE + 30 * (min(0,gas_brake_threshold) - self.EV_GAS_BRAKE_THRESHOLD_MIN_V)) # results in max brake command of around 418, based on a brake cmd = 350 test from 55mph to 0
    self.GAS_LOOKUP_BP = [gas_brake_threshold, 0., self.ACCEL_MAX]
    self.BRAKE_LOOKUP_BP = [self.ACCEL_MIN, gas_brake_threshold]
    self.BRAKE_LOOKUP_V = [max_brake, 0]
    return gas_brake_threshold

class CAR:
  HOLDEN_ASTRA = "HOLDEN ASTRA RS-V BK 2017"
  VOLT = "CHEVROLET VOLT PREMIER 2017"
  CADILLAC_ATS = "CADILLAC ATS Premium Performance 2018"
  MALIBU = "CHEVROLET MALIBU PREMIER 2017"
  ACADIA = "GMC ACADIA DENALI 2018"
  BUICK_REGAL = "BUICK REGAL ESSENCE 2018"
  ESCALADE_ESV = "CADILLAC ESCALADE ESV 2016"

class Footnote(Enum):
  OBD_II = CarFootnote(
    'Requires an <a href="https://comma.ai/shop/products/comma-car-harness">OBD-II car harness</a> and ' +
    '<a href="https://github.com/commaai/openpilot/wiki/GM#hardware">community built ASCM harness</a>. ' +
    '<b><i>NOTE: disconnecting the ASCM disables Automatic Emergency Braking (AEB).</i></b>',
    Column.MODEL)


CAR_INFO: Dict[str, Union[CarInfo, List[CarInfo]]] = {
  CAR.HOLDEN_ASTRA: CarInfo("Holden Astra 2017", "Adaptive Cruise"),
  CAR.VOLT: CarInfo("Chevrolet Volt 2017-18", "Adaptive Cruise", footnotes=[Footnote.OBD_II], min_enable_speed=0),
  CAR.CADILLAC_ATS: CarInfo("Cadillac ATS Premium Performance 2018", "Adaptive Cruise"),
  CAR.MALIBU: CarInfo("Chevrolet Malibu Premier 2017", "Adaptive Cruise"),
  CAR.ACADIA: CarInfo("GMC Acadia 2018", "Adaptive Cruise", video_link="https://www.youtube.com/watch?v=0ZN6DdsBUZo", footnotes=[Footnote.OBD_II]),
  CAR.BUICK_REGAL: CarInfo("Buick Regal Essence 2018", "Adaptive Cruise"),
  CAR.ESCALADE_ESV: CarInfo("Cadillac Escalade ESV 2016", "ACC + LKAS", footnotes=[Footnote.OBD_II]),
}

class CruiseButtons:
  INIT = 0
  UNPRESS = 1
  RES_ACCEL = 2
  SET_DECEL = 3
  MAIN = 5
  CANCEL = 6

class AccState:
  OFF = 0
  ACTIVE = 1
  FAULTED = 3
  STANDSTILL = 4

class CanBus:
  POWERTRAIN = 0
  OBSTACLE = 1
  CAMERA = 2
  CHASSIS = 2
  SW_GMLAN = 3
  LOOPBACK = 128 # GM: EPS fault workaround (#22404)

FINGERPRINTS = {
  # Astra BK MY17, ASCM unplugged
  CAR.HOLDEN_ASTRA: [{
    190: 8, 193: 8, 197: 8, 199: 4, 201: 8, 209: 7, 211: 8, 241: 6, 249: 8, 288: 5, 298: 8, 304: 1, 309: 8, 311: 8, 313: 8, 320: 3, 328: 1, 352: 5, 381: 6, 384: 4, 386: 8, 388: 8, 393: 8, 398: 8, 401: 8, 413: 8, 417: 8, 419: 8, 422: 1, 426: 7, 431: 8, 442: 8, 451: 8, 452: 8, 453: 8, 455: 7, 456: 8, 458: 5, 479: 8, 481: 7, 485: 8, 489: 8, 497: 8, 499: 3, 500: 8, 501: 8, 508: 8, 528: 5, 532: 6, 554: 3, 560: 8, 562: 8, 563: 5, 564: 5, 565: 5, 567: 5, 647: 5, 707: 8, 715: 8, 723: 8, 753: 5, 761: 7, 806: 1, 810: 8, 840: 5, 842: 5, 844: 8, 866: 4, 961: 8, 969: 8, 977: 8, 979: 8, 985: 5, 1001: 8, 1009: 8, 1011: 6, 1017: 8, 1019: 3, 1020: 8, 1105: 6, 1217: 8, 1221: 5, 1225: 8, 1233: 8, 1249: 8, 1257: 6, 1259: 8, 1261: 7, 1263: 4, 1265: 8, 1267: 8, 1280: 4, 1300: 8, 1328: 4, 1417: 8, 1906: 7, 1907: 7, 1908: 7, 1912: 7, 1919: 7,
  }],
  CAR.VOLT: [
  # Volt Premier w/ ACC 2017
  {
    170: 8, 171: 8, 189: 7, 190: 6, 193: 8, 197: 8, 199: 4, 201: 8, 209: 7, 211: 2, 241: 6, 288: 5, 298: 8, 304: 1, 308: 4, 309: 8, 311: 8, 313: 8, 320: 3, 328: 1, 352: 5, 381: 6, 384: 4, 386: 8, 388: 8, 389: 2, 390: 7, 417: 7, 419: 1, 426: 7, 451: 8, 452: 8, 453: 6, 454: 8, 456: 8, 479: 3, 481: 7, 485: 8, 489: 8, 493: 8, 495: 4, 497: 8, 499: 3, 500: 6, 501: 8, 508: 8, 528: 4, 532: 6, 546: 7, 550: 8, 554: 3, 558: 8, 560: 8, 562: 8, 563: 5, 564: 5, 565: 5, 566: 5, 567: 3, 568: 1, 573: 1, 577: 8, 578: 8, 608: 8, 609: 6, 610: 6, 611: 6, 612: 8, 613: 8, 647: 3, 707: 8, 711: 6, 715: 8, 717: 5, 761: 7, 810: 8, 840: 5, 842: 5, 844: 8, 866: 4, 869: 4, 880: 6, 961: 8, 967: 4, 969: 8, 977: 8, 979: 7, 988: 6, 989: 8, 995: 7, 1001: 8, 1005: 6, 1009: 8, 1017: 8, 1019: 2, 1020: 8, 1033: 7, 1034: 7, 1105: 6, 1187: 4, 1217: 8, 1221: 5, 1223: 3, 1225: 7, 1227: 4, 1233: 8, 1249: 8, 1257: 6, 1265: 8, 1267: 1, 1273: 3, 1275: 3, 1280: 4, 1296: 4, 1300: 8, 1322: 6, 1323: 4, 1328: 4, 1417: 8, 1516: 8, 1601: 8, 1618: 8, 1905: 7, 1906: 7, 1907: 7, 1910: 7, 1912: 7, 1922: 7, 1927: 7, 1930: 7, 2016: 8, 2018: 8, 2020: 8, 2024: 8, 2028: 8
  },
  # Volt Premier w/ ACC 2018
  {
    170: 8, 171: 8, 189: 7, 190: 6, 193: 8, 197: 8, 199: 4, 201: 8, 209: 7, 211: 2, 241: 6, 288: 5, 298: 8, 304: 1, 308: 4, 309: 8, 311: 8, 313: 8, 320: 3, 328: 1, 352: 5, 381: 6, 384: 4, 386: 8, 388: 8, 389: 2, 390: 7, 417: 7, 419: 1, 426: 7, 451: 8, 452: 8, 453: 6, 454: 8, 456: 8, 479: 3, 481: 7, 485: 8, 489: 8, 493: 8, 495: 4, 497: 8, 499: 3, 500: 6, 501: 8, 508: 8, 528: 4, 532: 6, 546: 7, 550: 8, 554: 3, 558: 8, 560: 8, 562: 8, 563: 5, 564: 5, 565: 5, 566: 5, 567: 3, 568: 1, 573: 1, 577: 8, 578: 8, 608: 8, 609: 6, 610: 6, 611: 6, 612: 8, 613: 8, 647: 3, 707: 8, 711: 6, 715: 8, 717: 5, 761: 7, 810: 8, 840: 5, 842: 5, 844: 8, 866: 4, 869: 4, 880: 6, 961: 8, 967: 4, 969: 8, 977: 8, 979: 7, 988: 6, 989: 8, 995: 7, 1001: 8, 1005: 6, 1009: 8, 1017: 8, 1019: 2, 1020: 8, 1033: 7, 1034: 7, 1105: 6, 1187: 4, 1217: 8, 1221: 5, 1223: 3, 1225: 7, 1227: 4, 1233: 8, 1249: 8, 1257: 6, 1265: 8, 1267: 1, 1273: 3, 1275: 3, 1280: 4, 1296: 4, 1300: 8, 1322: 6, 1323: 4, 1328: 4, 1417: 8, 1516: 8, 1601: 8, 1618: 8, 1905: 7, 1906: 7, 1907: 7, 1910: 7, 1912: 7, 1922: 7, 1927: 7, 1930: 7, 2016: 8, 2018: 8, 2020: 8, 2024: 8, 2028: 8
  }],
  CAR.BUICK_REGAL : [
  # Regal TourX Essence w/ ACC 2018
  {
    190: 8, 193: 8, 197: 8, 199: 4, 201: 8, 209: 7, 211: 8, 241: 6, 249: 8, 288: 5, 298: 8, 304: 1, 309: 8, 311: 8, 313: 8, 320: 3, 322: 7, 328: 1, 352: 5, 381: 6, 384: 4, 386: 8, 388: 8, 393: 7, 398: 8, 407: 7, 413: 8, 417: 8, 419: 8, 422: 4, 426: 8, 431: 8, 442: 8, 451: 8, 452: 8, 453: 8, 455: 7, 456: 8, 463: 3, 479: 8, 481: 7, 485: 8, 487: 8, 489: 8, 495: 8, 497: 8, 499: 3, 500: 8, 501: 8, 508: 8, 528: 5, 532: 6, 554: 3, 560: 8, 562: 8, 563: 5, 564: 5, 565: 5, 567: 5, 569: 3, 573: 1, 577: 8, 578: 8, 579: 8, 587: 8, 608: 8, 609: 6, 610: 6, 611: 6, 612: 8, 613: 8, 647: 3, 707: 8, 715: 8, 717: 5, 753: 5, 761: 7, 810: 8, 840: 5, 842: 5, 844: 8, 866: 4, 869: 4, 880: 6, 882: 8, 884: 8, 890: 1, 892: 2, 893: 2, 894: 1, 961: 8, 967: 8, 969: 8, 977: 8, 979: 8, 985: 8, 1001: 8, 1005: 6, 1009: 8, 1011: 8, 1013: 3, 1017: 8, 1020: 8, 1024: 8, 1025: 8, 1026: 8, 1027: 8, 1028: 8, 1029: 8, 1030: 8, 1031: 8, 1032: 2, 1033: 7, 1034: 7, 1105: 6, 1217: 8, 1221: 5, 1223: 8, 1225: 7, 1233: 8, 1249: 8, 1257: 6, 1259: 8, 1261: 8, 1263: 8, 1265: 8, 1267: 8, 1271: 8, 1280: 4, 1296: 4, 1300: 8, 1322: 6, 1328: 4, 1417: 8, 1601: 8, 1602: 8, 1603: 7, 1611: 8, 1618: 8, 1906: 8, 1907: 7, 1912: 7, 1914: 7, 1916: 7, 1919: 7, 1930: 7, 2016: 8, 2018: 8, 2019: 8, 2024: 8, 2026: 8
  }],
  CAR.CADILLAC_ATS: [
  # Cadillac ATS Coupe Premium Performance 3.6L RWD w/ ACC 2018
  {
    190: 6, 193: 8, 197: 8, 199: 4, 201: 8, 209: 7, 211: 2, 241: 6, 249: 8, 288: 5, 298: 8, 304: 1, 309: 8, 311: 8, 313: 8, 320: 3, 322: 7, 328: 1, 352: 5, 368: 3, 381: 6, 384: 4, 386: 8, 388: 8, 393: 7, 398: 8, 401: 8, 407: 7, 413: 8, 417: 7, 419: 1, 422: 4, 426: 7, 431: 8, 442: 8, 451: 8, 452: 8, 453: 6, 455: 7, 456: 8, 462: 4, 479: 3, 481: 7, 485: 8, 487: 8, 489: 8, 491: 2, 493: 8, 497: 8, 499: 3, 500: 6, 501: 8, 508: 8, 510: 8, 528: 5, 532: 6, 534: 2, 554: 3, 560: 8, 562: 8, 563: 5, 564: 5, 565: 5, 567: 5, 573: 1, 577: 8, 608: 8, 609: 6, 610: 6, 611: 6, 612: 8, 613: 8, 647: 6, 707: 8, 715: 8, 717: 5, 719: 5, 723: 2, 753: 5, 761: 7, 801: 8, 804: 3, 810: 8, 840: 5, 842: 5, 844: 8, 866: 4, 869: 4, 880: 6, 882: 8, 890: 1, 892: 2, 893: 2, 894: 1, 961: 8, 967: 4, 969: 8, 977: 8, 979: 8, 985: 5, 1001: 8, 1005: 6, 1009: 8, 1011: 6, 1013: 3, 1017: 8, 1019: 2, 1020: 8, 1033: 7, 1034: 7, 1105: 6, 1217: 8, 1221: 5, 1223: 3, 1225: 7, 1233: 8, 1241: 3, 1249: 8, 1257: 6, 1259: 8, 1261: 7, 1263: 4, 1265: 8, 1267: 1, 1271: 8, 1280: 4, 1296: 4, 1300: 8, 1322: 6, 1323: 4, 1328: 4, 1417: 8, 1601: 8, 1904: 7, 1906: 7, 1907: 7, 1912: 7, 1916: 7, 1917: 7, 1918: 7, 1919: 7, 1920: 7, 1930: 7, 2016: 8, 2024: 8
  }],
  CAR.MALIBU: [
  # Malibu Premier w/ ACC 2017
  {
    190: 6, 193: 8, 197: 8, 199: 4, 201: 8, 209: 7, 211: 2, 241: 6, 249: 8, 288: 5, 298: 8, 304: 1, 309: 8, 311: 8, 313: 8, 320: 3, 328: 1, 352: 5, 381: 6, 384: 4, 386: 8, 388: 8, 393: 7, 398: 8, 407: 7, 413: 8, 417: 7, 419: 1, 422: 4, 426: 7, 431: 8, 442: 8, 451: 8, 452: 8, 453: 6, 455: 7, 456: 8, 479: 3, 481: 7, 485: 8, 487: 8, 489: 8, 495: 4, 497: 8, 499: 3, 500: 6, 501: 8, 508: 8, 510: 8, 528: 5, 532: 6, 554: 3, 560: 8, 562: 8, 563: 5, 564: 5, 565: 5, 567: 5, 573: 1, 577: 8, 608: 8, 609: 6, 610: 6, 611: 6, 612: 8, 613: 8, 647: 6, 707: 8, 715: 8, 717: 5, 753: 5, 761: 7, 810: 8, 840: 5, 842: 5, 844: 8, 866: 4, 869: 4, 880: 6, 961: 8, 969: 8, 977: 8, 979: 8, 985: 5, 1001: 8, 1005: 6, 1009: 8, 1013: 3, 1017: 8, 1019: 2, 1020: 8, 1033: 7, 1034: 7, 1105: 6, 1217: 8, 1221: 5, 1223: 2, 1225: 7, 1233: 8, 1249: 8, 1257: 6, 1265: 8, 1267: 1, 1280: 4, 1296: 4, 1300: 8, 1322: 6, 1323: 4, 1328: 4, 1417: 8, 1601: 8, 1906: 7, 1907: 7, 1912: 7, 1919: 7, 1930: 7, 2016: 8, 2024: 8,
  }],
  CAR.ACADIA: [
  # Acadia Denali w/ACC 2018
  {
    190: 6, 192: 5, 193: 8, 197: 8, 199: 4, 201: 6, 208: 8, 209: 7, 211: 2, 241: 6, 249: 8, 288: 5, 289: 1, 290: 1, 298: 8, 304: 8, 309: 8, 313: 8, 320: 8, 322: 7, 328: 1, 352: 7, 368: 8, 381: 8, 384: 8, 386: 8, 388: 8, 393: 8, 398: 8, 413: 8, 417: 7, 419: 1, 422: 4, 426: 7, 431: 8, 442: 8, 451: 8, 452: 8, 453: 6, 454: 8, 455: 7, 458: 8, 460: 4, 462: 4, 463: 3, 479: 3, 481: 7, 485: 8, 489: 5, 497: 8, 499: 3, 500: 6, 501: 8, 508: 8, 510: 8, 512: 3, 530: 8, 532: 6, 534: 2, 554: 3, 560: 8, 562: 8, 563: 5, 564: 5, 567: 5, 568: 2, 573: 1, 608: 8, 609: 6, 610: 6, 611: 6, 612: 8, 613: 8, 647: 6, 707: 8, 715: 8, 717: 5, 753: 5, 761: 7, 789: 5, 800: 6, 801: 8, 803: 8, 804: 3, 805: 8, 832: 8, 840: 5, 842: 5, 844: 8, 866: 4, 869: 4, 880: 6, 961: 8, 969: 8, 977: 8, 979: 8, 985: 5, 1001: 8, 1003: 5, 1005: 6, 1009: 8, 1017: 8, 1020: 8, 1033: 7, 1034: 7, 1105: 6, 1217: 8, 1221: 5, 1225: 8, 1233: 8, 1249: 8, 1257: 6, 1265: 8, 1267: 1, 1280: 4, 1296: 4, 1300: 8, 1322: 6, 1328: 4, 1417: 8, 1906: 7, 1907: 7, 1912: 7, 1914: 7, 1918: 7, 1919: 7, 1920: 7, 1930: 7
  },
  # Acadia Denali w/ /ACC 2018
  {
    190: 6, 193: 8, 197: 8, 199: 4, 201: 8, 208: 8, 209: 7, 211: 2, 241: 6, 249: 8, 288: 5, 289: 8, 298: 8, 304: 1, 309: 8, 313: 8, 320: 3, 322: 7, 328: 1, 338: 6, 340: 6, 352: 5, 381: 8, 384: 4, 386: 8, 388: 8, 393: 8, 398: 8, 413: 8, 417: 7, 419: 1, 422: 4, 426: 7, 431: 8, 442: 8, 451: 8, 452: 8, 453: 6, 454: 8, 455: 7, 462: 4, 463: 3, 479: 3, 481: 7, 485: 8, 489: 8, 497: 8, 499: 3, 500: 6, 501: 8, 508: 8, 510: 8, 532: 6, 554: 3, 560: 8, 562: 8, 563: 5, 564: 5, 567: 5, 573: 1, 577: 8, 608: 8, 609: 6, 610: 6, 611: 6, 612: 8, 613: 8, 647: 6, 707: 8, 715: 8, 717: 5, 753: 5, 761: 7, 840: 5, 842: 5, 844: 8, 866: 4, 869: 4, 880: 6, 961: 8, 969: 8, 977: 8, 979: 8, 985: 5, 1001: 8, 1005: 6, 1009: 8, 1017: 8, 1020: 8, 1033: 7, 1034: 7, 1105: 6, 1217: 8, 1221: 5, 1225: 8, 1233: 8, 1249: 8, 1257: 6, 1265: 8, 1267: 1, 1280: 4, 1296: 4, 1300: 8, 1322: 6, 1328: 4, 1417: 8, 1601: 8, 1906: 7, 1907: 7, 1912: 7, 1914: 7, 1919: 7, 1920: 7, 1930: 7, 2016: 8, 2024: 8
  }],
  CAR.ESCALADE_ESV: [
  {
    309: 1, 848: 8, 849: 8, 850: 8, 851: 8, 852: 8, 853: 8, 854: 3, 1056: 6, 1057: 8, 1058: 8, 1059: 8, 1060: 8, 1061: 8, 1062: 8, 1063: 8, 1064: 8, 1065: 8, 1066: 8, 1067: 8, 1068: 8, 1120: 8, 1121: 8, 1122: 8, 1123: 8, 1124: 8, 1125: 8, 1126: 8, 1127: 8, 1128: 8, 1129: 8, 1130: 8, 1131: 8, 1132: 8, 1133: 8, 1134: 8, 1135: 8, 1136: 8, 1137: 8, 1138: 8, 1139: 8, 1140: 8, 1141: 8, 1142: 8, 1143: 8, 1146: 8, 1147: 8, 1148: 8, 1149: 8, 1150: 8, 1151: 8, 1216: 8, 1217: 8, 1218: 8, 1219: 8, 1220: 8, 1221: 8, 1222: 8, 1223: 8, 1224: 8, 1225: 8, 1226: 8, 1232: 8, 1233: 8, 1234: 8, 1235: 8, 1236: 8, 1237: 8, 1238: 8, 1239: 8, 1240: 8, 1241: 8, 1242: 8, 1787: 8, 1788: 8
  }],
}

ECU_FINGERPRINT = {
  Ecu.fwdCamera: [384, 715]
}

STEER_THRESHOLD = 1.0

DBC = {
  CAR.HOLDEN_ASTRA: dbc_dict('gm_global_a_powertrain_generated', 'gm_global_a_object', chassis_dbc='gm_global_a_chassis'),
  CAR.VOLT: dbc_dict('gm_global_a_powertrain_generated', 'gm_global_a_object', chassis_dbc='gm_global_a_chassis'),
  CAR.MALIBU: dbc_dict('gm_global_a_powertrain_generated', 'gm_global_a_object', chassis_dbc='gm_global_a_chassis'),
  CAR.ACADIA: dbc_dict('gm_global_a_powertrain_generated', 'gm_global_a_object', chassis_dbc='gm_global_a_chassis'),
  CAR.CADILLAC_ATS: dbc_dict('gm_global_a_powertrain_generated', 'gm_global_a_object', chassis_dbc='gm_global_a_chassis'),
  CAR.BUICK_REGAL: dbc_dict('gm_global_a_powertrain_generated', 'gm_global_a_object', chassis_dbc='gm_global_a_chassis'),
  CAR.ESCALADE_ESV: dbc_dict('gm_global_a_powertrain_generated', 'gm_global_a_object', chassis_dbc='gm_global_a_chassis'),
}

def main():
  for member, value in vars(CAR).items():
    if not member.startswith("_"):
      print(value)


if __name__ == "__main__":
  main()
