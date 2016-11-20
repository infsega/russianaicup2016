from model.ActionType import ActionType
from model.Game import Game
from model.Move import Move
from model.Wizard import Wizard
from model.World import World
from model.LaneType import LaneType
from model.Faction import Faction

import math
import random

WAYPOINT_RADIUS = 100.0
LOW_HP_FACTOR = 0.5


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

    def initialize_tick(self, me: Wizard, world: World, game: Game, move: Move):
        self.me = me
        self.world = world
        self.game = game
        self.current_move = move

    def get_nearest_target(self):
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

    def go_to_unit(self, unit):
        self.go_to(unit.x, unit.y)

    def go_to(self, x, y):
        angle = self.me.get_angle_to(x, y)
        self.current_move.turn = angle
        if abs(angle) < self.game.staff_sector / 4.0:
            self.current_move.speed = self.game.wizard_forward_speed

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

    def move(self, me: Wizard, world: World, game: Game, move: Move):
        self.initialize_strategy(me, game)
        self.initialize_tick(me, world, game, move)

        move.strafe_speed = random.choice([game.wizard_strafe_speed, -game.wizard_strafe_speed])

        if me.life < me.max_life * LOW_HP_FACTOR:
            print("Retreat")
            self.go_to_unit(self.get_previous_waypoint())
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
                return

        print("Go to next waypoint")
        self.go_to_unit(self.get_next_waypoint())
