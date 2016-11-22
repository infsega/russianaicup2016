from model.ActionType import ActionType
from model.Game import Game
from model.Move import Move
from model.Wizard import Wizard
from model.World import World
from model.LaneType import LaneType
from model.Faction import Faction
from model.LivingUnit import LivingUnit
from model.Building import Building
from model.BuildingType import BuildingType
from model.Minion import Minion
from model.MinionType import MinionType
from model.Message import Message

import math
import random

WAYPOINT_RADIUS = 150.0
LOW_HP_FACTOR = 0.25


def intersection_point(p, v, w):
    l2 = (v.x-w.x)**2 + (v.y-w.y)**2
    if l2 == 0:
        return v
    t = ((p.x - v.x) * (w.x - v.x) + (p.y - v.y) * (w.y - v.y)) / l2
    t = max(0, min(1, t))
    return Point2D(v.x + t * (w.x - v.x), v.y + t * (w.y - v.y))


def distance_to_segment(p, v, w):
    return p.get_distance_to_unit(intersection_point(p, v, w))


def collide(x, y, radius, unit: LivingUnit):
    return unit.get_distance_to(x, y) < unit.radius + radius


class Point2D:
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def get_distance_to(self, x, y):
        return math.hypot(x - self.x, y - self.y)

    def get_distance_to_unit(self, unit):
        return self.get_distance_to(unit.x, unit.y)


def target_priority(target):
    if target is None:
        return 0
    if target is Minion:
        if target.type == MinionType.ORC_WOODCUTTER:
            return 1
        else:
            return 2
    if target is Building:
        return 3
    return 4


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
        self.last_waypoint = None

    def setup_strafe(self):
        if self.strafe_line == 0:
            self.strafe_line = random.randint(20, 40)
            self.strafe_dir = -self.strafe_dir
        strafe_speed = random.uniform(self.game.wizard_strafe_speed / 2.0, self.game.wizard_strafe_speed)
        self.current_move.strafe_speed = self.strafe_dir * strafe_speed
        self.strafe_line -= 1

    def initialize_tick(self, me: Wizard, world: World, game: Game, move: Move):
        self.me = me
        self.world = world
        self.game = game
        self.current_move = move

    def select_target(self, target1: LivingUnit, target2: LivingUnit):
        priority1 = target_priority(target1)
        priority2 = target_priority(target2)
        if priority1 > priority2:
            return target1
        if priority2 > priority1:
            return target2

        angle1 = abs(self.me.get_angle_to_unit(target1))
        angle2 = abs(self.me.get_angle_to_unit(target2))
        angle_criteria1 = (angle1 < self.game.staff_sector)
        angle_criteria2 = (angle2 < self.game.staff_sector)

        if angle_criteria1 < angle_criteria2:
            return target1
        if angle_criteria1 > angle_criteria2:
            return target2

        if angle_criteria1 and angle_criteria2:
            if target1.life < target2.life:
                return target1
            if target2.life < target1.life:
                return target2

        distance1 = self.me.get_distance_to_unit(target1) - target1.radius * 0.6
        distance2 = self.me.get_distance_to_unit(target2) - target2.radius * 0.6
        if distance1 < distance2:
            return target1
        else:
            return target2

    def get_nearest_target(self) -> LivingUnit:
        attacker = self.get_closest_attacker()
        if attacker is not None:
            return attacker
        nearest_target = None
        for target in self.enemy_units():
            distance = self.me.get_distance_to_unit(target) - target.radius  # allow minimal collision
            if distance > self.me.cast_range:
                continue
            nearest_target = self.select_target(nearest_target, target)
        return nearest_target

    def get_unit_distance_on_lane(self, lane: LaneType, unit):
        wp = self.waypoints_by_lane[lane]
        min_segment_distance = None
        unit_distance_on_lane = None
        path_length = 0
        for i in range(len(wp) - 1):
            segment_distance = distance_to_segment(unit, wp[i], wp[i+1])
            if (min_segment_distance is None) or (min_segment_distance > segment_distance):
                min_segment_distance = segment_distance
                path_section = intersection_point(unit, wp[i], wp[i+1])
                unit_distance_on_lane = path_length + wp[i].get_distance_to_unit(path_section)
            path_length += wp[i].get_distance_to_unit(wp[i+1])
        return unit_distance_on_lane

    def get_unit_distance_to_lane(self, lane: LaneType, unit):
        wp = self.waypoints_by_lane[lane]
        return min(distance_to_segment(unit, wp[i], wp[i+1]) for i in range(len(wp) - 1))

    def get_unit_lane(self, unit):
        if (unit is Building) and (unit.type == BuildingType.FACTION_BASE):
            return None
        closest_lane = None
        distance_to_closest_lane = None
        for lane in [LaneType.TOP, LaneType.MIDDLE, LaneType.BOTTOM]:
            distance_to_lane = self.get_unit_distance_to_lane(lane, unit)
            if (closest_lane is None) or (distance_to_closest_lane > distance_to_lane):
                closest_lane = lane
                distance_to_closest_lane = distance_to_lane
        return closest_lane

    def get_position(self, unit):
        lane = self.get_unit_lane(unit)
        if lane is None:
            return lane, 0
        return lane, self.get_unit_distance_on_lane(lane, unit)

    def get_vanguard(self) -> LivingUnit:
        vanguard = None
        vanguard_distance = None
        for ally in self.allies():
            lane, distance = self.get_position(ally)
            if lane not in [None, self.lane]:
                continue
            if (vanguard_distance is None) or (distance > vanguard_distance):
                vanguard = ally
                vanguard_distance = distance
        return vanguard

    def get_unit_free_attack_distance(self, unit):
        distance = self.me.get_distance_to_unit(unit)
        attack_distance = self.get_attack_distance(unit) + self.me.radius
        return distance - 1.1 * attack_distance

    def get_closest_attacker(self):
        closest_attacker = None
        closest_attacker_distance = None
        for attacker in self.enemy_units():
            attacker_distance = self.get_unit_free_attack_distance(attacker)
            if attacker_distance > 0:
                continue
            if (closest_attacker is None) or attacker_distance < closest_attacker_distance:
                closest_attacker = attacker
                closest_attacker_distance = attacker_distance
        return closest_attacker

    def enemy_units(self):
        targets = self.world.buildings + self.world.wizards + self.world.minions
        return [unit for unit in targets if unit.faction not in [Faction.NEUTRAL, self.me.faction]]

    def allies(self):
        units = self.world.buildings + self.world.wizards + self.world.minions
        return [unit for unit in units if (unit.faction == self.me.faction) and (unit.id != self.me.id)]

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

    def initialize_strategy(self, me: Wizard, game: Game, move: Move):
        if self.game is not None:
            return
        random.seed(game.random_seed)
        map_size = game.map_size
        self.waypoints_by_lane = {
            LaneType.MIDDLE: [
                Point2D(100.0, map_size - 100.0),
                random.choice([Point2D(600.0, map_size - 200.0), Point2D(200.0, map_size - 600.0)]),
                Point2D(800.0, map_size - 800.0),
                Point2D(map_size - 1400.0, 1400.0)
            ],
            LaneType.TOP: [
                Point2D(50.0, map_size - 800.0),
                Point2D(200.0, map_size * 0.75),
                Point2D(200.0, map_size * 0.50),
                Point2D(200.0, map_size * 0.25),
                Point2D(200.0, 800.0),
                Point2D(400.0, 400.0),
                Point2D(800.0, 200.0),
                Point2D(map_size * 0.25, 200.0),
                Point2D(map_size * 0.50, 200.0),
                Point2D(map_size * 0.65, 200.0),
                # Point2D(map_size * 0.75, 200.0),
                # Point2D(map_size - 800.0, 200.0)
            ],
            LaneType.BOTTOM: [
                Point2D(800.0, map_size - 50.0),
                Point2D(map_size * 0.50, map_size - 200.0),
                Point2D(map_size * 0.75, map_size - 200.0),
                Point2D(map_size - 800.0, map_size - 200.0),
                Point2D(map_size - 400.0, map_size - 400.0),
                Point2D(map_size - 200.0, map_size - 800.0),
                Point2D(map_size - 200.0, map_size * 0.75),
                Point2D(map_size - 200.0, map_size * 0.50),
                Point2D(map_size - 200.0, map_size * 0.35),
                # Point2D(map_size - 200.0, map_size * 0.25),
                # Point2D(map_size - 200.0, 600.0)
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

        if me.master:
            move.messages = [
                Message(LaneType.TOP, None, None),
                Message(LaneType.BOTTOM, None, None),
                Message(LaneType.MIDDLE, None, None),
                Message(self.lane, None, None)
            ]
        else:
            for msg in me.messages:
                if msg is None:
                    continue
                if msg.lane in [LaneType.TOP, LaneType.MIDDLE, LaneType.BOTTOM]:
                    self.lane = msg.lane

        # self.lane = LaneType.BOTTOM
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

    def go_to_next_waypoint(self):
        if self.me.get_distance_to_unit(self.waypoints[-1]) < WAYPOINT_RADIUS:
            return
        next_waypoint = self.get_next_waypoint()
        if next_waypoint is None:
            return
        if next_waypoint != self.last_waypoint:
            self.last_waypoint = next_waypoint
            print("Go to next waypoint")

        distance_to_check = self.me.radius * 0.5
        x = self.me.x + math.cos(self.me.angle) * distance_to_check
        y = self.me.y + math.sin(self.me.angle) * distance_to_check
        for tree in self.world.trees:
            if collide(x, y, self.me.radius, tree):
                angle = self.me.get_angle_to_unit(tree)
                self.current_move.turn = angle
                if abs(angle) < self.game.staff_sector / 2.0:
                    self.current_move.action = ActionType.STAFF
                return
        for unit in self.world.buildings + self.world.wizards + self.world.minions:
            if unit.id == self.me.id:
                continue
            if collide(x, y, self.me.radius, unit):
                print("Cannot move")
                return
        angle = self.me.get_angle_to(next_waypoint.x, next_waypoint.y)
        self.current_move.turn = angle
        if abs(angle) < self.game.staff_sector / 4.0:
            self.current_move.speed = self.game.wizard_forward_speed

    def retreat(self):
        distance_to_check = self.me.radius * 0.5
        x = self.me.x - math.cos(self.me.angle) * distance_to_check
        y = self.me.y - math.sin(self.me.angle) * distance_to_check

        x_locked = (x - self.me.radius < 0) or (x + self.me.radius > self.game.map_size)
        y_locked = (y - self.me.radius < 0) or (y + self.me.radius > self.game.map_size)
        if x_locked or y_locked:
            return False

        for unit in self.world.buildings + self.world.minions + self.world.trees + self.world.wizards:
            if unit.id != self.me.id:
                if collide(x, y, self.me.radius, unit):
                    return False

        self.current_move.speed = -self.game.wizard_backward_speed
        return True

    def move(self, me: Wizard, world: World, game: Game, move: Move):
        self.initialize_strategy(me, game, move)
        self.initialize_tick(me, world, game, move)

        self.setup_strafe()

        move_forward = True

        if me.life < me.max_life * LOW_HP_FACTOR:
            if self.retreat():
                print("Medic!")
                return
            print("Medic needed, but no chance to retreat")
            move_forward = False

        vanguard = self.get_vanguard()
        if vanguard is not None:
            vanguard_distance = self.get_unit_distance_on_lane(self.lane, vanguard)
            my_distance = self.get_unit_distance_on_lane(self.lane, self.me)
            if my_distance + 100 > vanguard_distance:
                if self.retreat():
                    print("There is no vanguard. Retreat.")
                else:
                    print("There is no vanguard. Cannot retreat")
                move_forward = False

        nearest_target = self.get_nearest_target()
        if nearest_target is not None:
            distance = me.get_distance_to_unit(nearest_target)
            if distance <= me.cast_range:
                angle = me.get_angle_to_unit(nearest_target)
                move.turn = angle
                if abs(angle) < game.staff_sector / 2.0:
                    if distance <= game.staff_range:
                        print("Hard attack")
                        move.action = ActionType.STAFF
                    else:
                        print("Attack")
                        move.action = ActionType.MAGIC_MISSILE
                    move.cast_angle = angle
                    move.min_cast_distance = distance - nearest_target.radius + game.magic_missile_radius

                if self.get_closest_attacker() is not None:
                    if self.retreat():
                        print("Under attack! Retreat")
                    else:
                        print("Under attack! Failed to retreat")

                return

        if move_forward:
            self.go_to_next_waypoint()
