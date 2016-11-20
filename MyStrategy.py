from model.ActionType import ActionType
from model.Game import Game
from model.Move import Move
from model.Wizard import Wizard
from model.World import World
from model.LaneType import LaneType
from model.Faction import Faction
from model.LivingUnit import LivingUnit
from model.Building import Building
from model.Minion import Minion
from model.MinionType import MinionType

import math
import random

WAYPOINT_RADIUS = 100.0
LOW_HP_FACTOR = 0.25


class Point2D:
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def get_distance_to(self, x, y):
        return math.hypot(x - self.x, y - self.y)

    def get_distance_to_unit(self, unit):
        return self.get_distance_to(unit.x, unit.y)


class MyStrategy:

    def __init__(self):
        self.lane = LaneType.TOP
        self.me = None
        self.world = None
        self.game = None
        self.current_move = None
        self.waypoints = None
        self.waypoints_by_lane = None
        self.strafe_line = 0
        self.strafe_dir = -1

    def setup_strafe(self):
        if self.strafe_line == 0:
            self.strafe_line = random.randint(1,6)
            self.strafe_dir  = -self.strafe_dir
        self.current_move.strafe_speed = self.strafe_dir * random.uniform(0, self.game.wizard_strafe_speed)
        self.strafe_line -= 1

    def initialize_tick(self, me: Wizard, world: World, game: Game, move: Move):
        self.me = me
        self.world = world
        self.game = game
        self.current_move = move

    def get_nearest_target(self) -> LivingUnit:
        targets = self.world.buildings + self.world.wizards + self.world.minions
        nearest_target = None
        nearest_target_distance = None
        for target in targets:
            if target.faction in [Faction.NEUTRAL, self.me.faction]:
                continue
            distance = self.me.get_distance_to_unit(target)
            if (nearest_target_distance is None) or (distance < nearest_target_distance):
                nearest_target = target
            nearest_target_distance = distance
        return nearest_target

    def get_unit_free_attack_distance(self, unit):
        distance = self.me.get_distance_to_unit(unit)
        attack_distance = self.get_attack_distance(unit)
        return distance - 1.1 * attack_distance

    def enemy_units(self):
        targets = self.world.buildings + self.world.wizards + self.world.minions
        return [unit for unit in targets if unit.faction not in [Faction.NEUTRAL, self.me.faction]]

    def get_free_attack_distance(self):
        return min([self.get_unit_free_attack_distance(unit) for unit in self.enemy_units()])

    def get_next_waypoint(self):
        last_waypoint = self.waypoints[-1]
        distance_to_last_waypoint = last_waypoint.get_distance_to_unit(self.me)
        for i in range(0, len(self.waypoints)-1):
            waypoint = self.waypoints[i]
            if waypoint.get_distance_to_unit(self.me) <= WAYPOINT_RADIUS:
                return self.waypoints[i + 1]
            if last_waypoint.get_distance_to_unit(waypoint) < distance_to_last_waypoint:
                return waypoint
        return last_waypoint

    def get_previous_waypoint(self):
        first_waypoint = self.waypoints[0]
        distance_to_first_waypoint = first_waypoint.get_distance_to_unit(self.me)
        for i in reversed(range(1, len(self.waypoints))):
            waypoint = self.waypoints[i]
            if waypoint.get_distance_to_unit(self.me) <= WAYPOINT_RADIUS:
                return self.waypoints[i - 1]
            if first_waypoint.get_distance_to_unit(waypoint) < distance_to_first_waypoint:
                return waypoint
        return first_waypoint

    def initialize_strategy(self, me: Wizard, game: Game):
        if self.game is not None:
            return
        random.seed(game.random_seed)
        map_size = game.map_size
        self.waypoints_by_lane = {
            LaneType.MIDDLE: [
                Point2D(100.0, map_size - 100.0),
                random.choice([Point2D(600.0, map_size - 200.0), Point2D(200.0, map_size - 600.0)]),
                Point2D(800.0, map_size - 800.0),
                Point2D(map_size - 600.0, 600.0)
            ],
            LaneType.TOP: [
                Point2D(100.0, map_size - 100.0),
                Point2D(100.0, map_size - 400.0),
                Point2D(200.0, map_size - 800.0),
                Point2D(200.0, map_size * 0.75),
                Point2D(200.0, map_size * 0.50),
                Point2D(200.0, map_size * 0.25),
                Point2D(200.0, 200.0),
                Point2D(map_size * 0.25, 200.0),
                Point2D(map_size * 0.50, 200.0),
                Point2D(map_size * 0.75, 200.0),
                Point2D(map_size - 200.0, 200.0)
            ],
            LaneType.BOTTOM: [
                Point2D(100.0, map_size - 100.0),
                Point2D(400.0, map_size - 100.0),
                Point2D(800.0, map_size - 200.0),
                Point2D(map_size * 0.25, map_size - 200.0),
                Point2D(map_size * 0.50, map_size - 200.0),
                Point2D(map_size * 0.75, map_size - 200.0),
                Point2D(map_size - 200.0, map_size - 200.0),
                Point2D(map_size - 200.0, map_size * 0.75),
                Point2D(map_size - 200.0, map_size * 0.50),
                Point2D(map_size - 200.0, map_size * 0.25),
                Point2D(map_size - 200.0, 200.0)
            ]
        }
        if me.id in [1, 2, 6, 7]:
            self.lane = LaneType.TOP
            print("TOP")
        elif me.id in [3, 8]:
            self.lane = LaneType.MIDDLE
            print("MIDDLE")
        else:
            self.lane = LaneType.BOTTOM
            print("BOTTOM")
        self.waypoints = self.waypoints_by_lane[self.lane]

    def get_attack_distance(self, unit):
        if unit is Wizard:
            return unit.staff_range
        elif unit is Building:
            return unit.attack_range
        elif unit is Minion:
            if unit.type == MinionType.ORC_WOODCUTTER:
                return self.game.orc_woodcutter_attack_range
            elif unit.type == MinionType.FETISH_BLOWDART:
                return self.game.fetish_blowdart_attack_range
        else:
            return 0

    def go_to_unit(self, unit, force=False):
        self.go_to(unit.x, unit.y)

    def go_to(self, x, y, force=False):
        angle = self.me.get_angle_to(x, y)
        self.current_move.turn = angle
        if force or (abs(angle) < self.game.staff_sector / 4.0):
            self.current_move.speed = self.game.wizard_forward_speed

    def move(self, me: Wizard, world: World, game: Game, move: Move):
        self.initialize_strategy(me, game)
        self.initialize_tick(me, world, game, move)

        self.setup_strafe()

        if me.life < me.max_life * LOW_HP_FACTOR:
            print("Retreat")
            self.go_to_unit(self.get_previous_waypoint(), force=True)
            return

        nearest_target = self.get_nearest_target()
        if nearest_target is not None:
            distance = me.get_distance_to_unit(nearest_target)
            if distance <= me.cast_range:
                angle = me.get_angle_to_unit(nearest_target)
                move.turn = angle
                print("Turn to target")

                if abs(angle) < game.staff_sector / 2.0:
                    print("Attack")
                    move.action = ActionType.MAGIC_MISSILE
                    move.cast_angle = angle
                    move.min_cast_distance = distance - nearest_target.radius + game.magic_missile_radius

                if self.get_free_attack_distance() < 0:
                    print("Keeping away")
                    self.go_to_unit(self.get_previous_waypoint(), force=True)

                return

        print("Go to next waypoint")
        self.go_to_unit(self.get_next_waypoint())
