import math
import unittest
from dataclasses import replace
from pathlib import Path

from worcalc.domain.calibration import METRES_TO_YARDS
from worcalc.domain.physics_solution import LaunchGeometry, PhysicsSolver
from worcalc.domain.ballistic_solution import BallisticSolutionEngine
from worcalc.domain.trajectory import TerrainProfilePoint as P


class PhysicsSolutionTests(unittest.TestCase):
    def test_vacuum_solution_matches_closed_form(self):
        solver=PhysicsSolver(100,0,9.81,LaunchGeometry(0,0,0,-8,45))
        x=100
        result=solver.solve(x*METRES_TO_YARDS,0)
        expected=math.degrees(math.asin(9.81*x/100**2))/2
        self.assertAlmostEqual(result.elevation_degrees,expected,places=8)
        self.assertAlmostEqual(result.flight_time_seconds,x/(100*math.cos(math.radians(expected))),places=8)

    def test_all_weapon_profiles_hit_elevated_targets_with_same_time(self):
        engine=BallisticSolutionEngine(Path(__file__).resolve().parents[1]/'war_of_rights_ballistic_ranges.csv')
        for cannon in ('3-inch Ordnance','10-pounder Parrott','12-pounder Napoleon'):
            for ammo in ('Shell','Case'):
                engine.set_weapon(cannon,ammo)
                for height in (-10,0,10):
                    with self.subTest(cannon=cannon,ammo=ammo,height=height):
                        solver=engine.physics
                        aim=solver.solve(300,height)
                        # Independently integrate velocity/position with RK4.
                        theta=math.radians(aim.elevation_degrees+solver.launch.angle_offset_deg)
                        state=[0,solver.launch.height_metres,solver.speed*math.cos(theta),solver.speed*math.sin(theta)]
                        dt=aim.flight_time_seconds/1000
                        def derivative(s):return [s[2],s[3],-solver.drag*s[2],-solver.gravity-solver.drag*s[3]]
                        for _ in range(1000):
                            a=derivative(state)
                            b=derivative([v+dt*k/2 for v,k in zip(state,a)])
                            c=derivative([v+dt*k/2 for v,k in zip(state,b)])
                            d=derivative([v+dt*k for v,k in zip(state,c)])
                            state=[v+dt*(aa+2*bb+2*cc+dd)/6 for v,aa,bb,cc,dd in zip(state,a,b,c,d)]
                        self.assertAlmostEqual(state[0],300/METRES_TO_YARDS,places=6)
                        self.assertAlmostEqual(state[1],height,places=6)

    def test_geometry_changes_solution_without_reference_table(self):
        solver=PhysicsSolver(370,.1)
        aim=solver.solve(300,0)
        shifted=replace(solver,launch=replace(solver.launch,angle_offset_deg=.68))
        self.assertAlmostEqual(shifted.solve(300,0).elevation_degrees,aim.elevation_degrees-.2)
        raised=replace(solver,launch=replace(solver.launch,height_metres=2))
        self.assertLess(raised.solve(300,0).elevation_degrees,aim.elevation_degrees)
        muzzle=replace(solver,launch=replace(solver.launch,forward_metres=1.2))
        result=muzzle.solve(300,8)
        self.assertAlmostEqual(muzzle.at_distance(300,result.elevation_degrees)[0],8,places=7)

    def test_obstruction_near_gun_and_near_target_is_not_ignored(self):
        solver=PhysicsSolver(370,.1)
        for distance in (1,295):
            result=solver.clearance(300,0,(P(0,0),P(distance,20),P(300,0)))
            self.assertTrue(result.obstructed)
            self.assertLess(result.first_obstruction_yards,distance)
            if distance == 1:
                self.assertIsNone(result.clearing_elevation_deg)
            else:
                self.assertIsNotNone(result.clearing_elevation_deg)
                self.assertGreater(result.clearing_elevation_deg,result.original_elevation_deg)
                self.assertGreater(result.height_above_target_metres,0)
                self.assertTrue(all(
                    sample.clearance_metres >= 0.01-1e-7
                    for sample in result.clearing_trajectory
                    if 0 < sample.distance_yards < 300
                ))

    def test_clear_arc_reaches_target_without_artificial_height_bias(self):
        solver=PhysicsSolver(370,.1)
        result=solver.clearance(300,5,tuple(P(d,100+5*d/300) for d in range(0,301,10)))
        self.assertFalse(result.obstructed)
        self.assertAlmostEqual(result.height_above_target_metres,0,places=7)
        self.assertAlmostEqual(result.impact_range_yards,300)
        for sample in result.original_trajectory:
            self.assertAlmostEqual(sample.shell_elevation_metres,100+solver.at_distance(sample.distance_yards,result.original_elevation_deg)[0])

    def test_limits_unknown_profiles_and_small_drag(self):
        solver=PhysicsSolver(370,.1)
        self.assertIsNone(solver.solve(10000,0))
        self.assertIsNone(solver.solve(100,1000))
        for v in (float('nan'),float('inf'),-1,0):
            with self.assertRaises(ValueError):solver.solve(v,0)
        with self.assertRaises(ValueError):solver.clearance(300,0,(P(0,0),P(50,0)))
        a=PhysicsSolver(370,0).solve(300,0)
        b=PhysicsSolver(370,1e-10).solve(300,0)
        self.assertAlmostEqual(a.elevation_degrees,b.elevation_degrees,places=7)
