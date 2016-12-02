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
from model.Projectile import Projectile
from model.ProjectileType import ProjectileType
from model.Tree import Tree
from model.Unit import Unit
from model.SkillType import SkillType
from model.StatusType import StatusType
from model.Bonus import Bonus
from model.BonusType import BonusType

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


def sectors_intersects(sector1, sector2):
    min1, max1 = sector1
    min2, max2 = sector2
    if max1 < min2:
        return False
    if min1 > max2:
        return False
    return True


def target_priority(target):
    if target is None:
        return 0
    if type(target) is Building:
        return 1
    if type(target) is Minion:
        if target.type == MinionType.ORC_WOODCUTTER:
            return 3
        else:
            return 2
    return 4

unit_class = {
    Minion: {
        MinionType.ORC_WOODCUTTER: "Orc",
        MinionType.FETISH_BLOWDART: "Fetish"
    },
    Building: {
        BuildingType.FACTION_BASE: "Base",
        BuildingType.GUARDIAN_TOWER: "Tower"
    },
    Projectile: {
        ProjectileType.MAGIC_MISSILE: "Missile",
        ProjectileType.FROST_BOLT: "Frost",
        ProjectileType.FIREBALL: "Fireball",
        ProjectileType.DART: "Dart"
    },
    Bonus : {
        BonusType.EMPOWER: "Empower",
        BonusType.HASTE: "Haste",
        BonusType.SHIELD: "Shield"
    }
}


def unit_class_str(unit):
    if type(unit) is Wizard:
        return "Wizard"
    if type(unit) is Tree:
        return "Tree"
    return unit_class[type(unit)][unit.type]


class Point2D:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.radius = 0

    def get_distance_to(self, x, y):
        return math.hypot(x - self.x, y - self.y)

    def get_distance_to_unit(self, unit):
        return self.get_distance_to(unit.x, unit.y)


def is_frozen(unit: LivingUnit):
    for status in unit.statuses:
        if status.type == StatusType.FROZEN:
            if status.remaining_duration_ticks > 5:
                return True
    return False


def predict_position(unit: Unit, ticks):
    return Point2D(
        unit.x + unit.speed_x * (0.5 * ticks),
        unit.y + unit.speed_y * (0.5 * ticks))


def can_be_frozen(target):
    if is_frozen(target):
        return False
    return type(target) not in [Building, Tree]


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
        self.angry_neutrals = set()
        self.last_tree = None
        self.last_skill = -1
        self.last_level = 0
        self.skills_to_learn = [
            SkillType.MAGICAL_DAMAGE_BONUS_PASSIVE_1,
            SkillType.MAGICAL_DAMAGE_BONUS_AURA_1,
            SkillType.MAGICAL_DAMAGE_BONUS_PASSIVE_2,
            SkillType.MAGICAL_DAMAGE_BONUS_AURA_2,
            SkillType.FROST_BOLT,
            SkillType.RANGE_BONUS_PASSIVE_1,
            SkillType.RANGE_BONUS_AURA_1,
            SkillType.RANGE_BONUS_PASSIVE_2,
            SkillType.RANGE_BONUS_AURA_2,
            SkillType.ADVANCED_MAGIC_MISSILE,
            SkillType.STAFF_DAMAGE_BONUS_PASSIVE_1,
            SkillType.STAFF_DAMAGE_BONUS_AURA_1,
            SkillType.STAFF_DAMAGE_BONUS_PASSIVE_2,
            SkillType.STAFF_DAMAGE_BONUS_AURA_2,
            SkillType.FIREBALL,
            SkillType.MOVEMENT_BONUS_FACTOR_PASSIVE_1,
            SkillType.MOVEMENT_BONUS_FACTOR_AURA_1,
            SkillType.MOVEMENT_BONUS_FACTOR_PASSIVE_2,
            SkillType.MOVEMENT_BONUS_FACTOR_AURA_2,
            SkillType.HASTE,
            SkillType.MAGICAL_DAMAGE_ABSORPTION_PASSIVE_1,
            SkillType.MAGICAL_DAMAGE_ABSORPTION_AURA_1,
            SkillType.MAGICAL_DAMAGE_ABSORPTION_PASSIVE_2,
            SkillType.MAGICAL_DAMAGE_ABSORPTION_AURA_2,
            SkillType.SHIELD
        ]
        self.advanced_missile = False
        self.has_frost_bolt = False
        self.has_fireball = False
        self.has_haste = False
        self.has_shield = False

    def unit_faction_str(self, unit: Unit):
        if unit.faction == self.me.faction:
            return "friend"
        elif unit.faction == Faction.NEUTRAL:
            return "neutral"
        elif unit.faction == Faction.OTHER:
            return "other"
        else:
            return "enemy"

    def unit_to_str(self, unit):
        if type(unit) is Point2D:
            return "Point(%0.1f, %0.1f)" % (unit.x, unit.y)
        elif type(unit) is Bonus:
            return "%s(%0.1f, %0.1f)" % (unit_class_str(unit), unit.x, unit.y)
        else:
            return "%s[%s](%0.1f, %0.1f)" % (unit_class_str(unit), self.unit_faction_str(unit), unit.x, unit.y)

    def can_strafe(self, strafe_direction):
        distance_to_check = self.me.radius * 0.1
        x = self.me.x + math.cos(self.me.angle + strafe_direction * math.pi / 2) * distance_to_check
        if not (self.me.radius < x < self.game.map_size - self.me.radius):
            print(self.world.tick_index, "X bump")
            return False
        y = self.me.y + math.sin(self.me.angle + strafe_direction * math.pi / 2) * distance_to_check
        if not (self.me.radius < y < self.game.map_size - self.me.radius):
            print(self.world.tick_index, "Y bump")
            return False

        for unit in self.world.buildings + self.world.trees + self.world.minions + self.world.wizards:
            if unit.id == self.me.id:
                continue
            if unit.get_distance_to(x, y) <= unit.radius + self.me.radius:
                print(self.world.tick_index, "Bump with %s" % self.unit_to_str(unit))
                return False

        return True

    def setup_strafe(self):
        if self.strafe_line == 0 or not self.can_strafe(self.strafe_dir):
            self.strafe_dir = -self.strafe_dir
            self.strafe_line = 60
        self.current_move.strafe_speed = self.strafe_dir * self.game.wizard_strafe_speed
        self.strafe_line -= 1

    def initialize_tick(self, me: Wizard, world: World, game: Game, move: Move):
        if self.me is None:
            self.initialize_strategy(me, game, move)
        self.me = me
        self.world = world
        self.game = game
        self.current_move = move

    def select_target(self, target1: LivingUnit, target2: LivingUnit):
        if target1 is None:
            return target2
        if target2 is None:
            return target1

        if self.can_cast_frost_bolt():
            can_be_frozen1 = can_be_frozen(target1)
            can_be_frozen2 = can_be_frozen(target2)
            if can_be_frozen1 and not can_be_frozen2:
                return target1
            if can_be_frozen2 and not can_be_frozen1:
                return target2

        turns_to_kill1 = math.ceil(target1.life / self.game.magic_missile_direct_damage)
        turns_to_kill2 = math.ceil(target2.life / self.game.magic_missile_direct_damage)

        if turns_to_kill1 < 3 <= turns_to_kill2:
            return target1
        if turns_to_kill2 < 3 <= turns_to_kill1:
            return target2

        priority1 = target_priority(target1)
        priority2 = target_priority(target2)
        if priority1 > priority2:
            return target1
        if priority2 > priority1:
            return target2

        angle_criteria1 = self.is_current_attack_angle(target1)
        angle_criteria2 = self.is_current_attack_angle(target2)

        if angle_criteria1 < angle_criteria2:
            return target1
        if angle_criteria1 > angle_criteria2:
            return target2

        if target1.life < target2.life:
            return target1
        if target2.life < target1.life:
            return target2

        ticks_to_turn1 = math.ceil(abs(self.me.get_angle_to_unit(target1)) / self.game.wizard_max_turn_angle)
        ticks_to_turn2 = math.ceil(abs(self.me.get_angle_to_unit(target2)) / self.game.wizard_max_turn_angle)
        if ticks_to_turn1 < ticks_to_turn2:
            return target1
        elif ticks_to_turn1 > ticks_to_turn2:
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
        if (type(unit) is Building) and (unit.type == BuildingType.FACTION_BASE):
            return None
        closest_lane = None
        distance_to_closest_lane = None
        for lane in [LaneType.TOP, LaneType.MIDDLE, LaneType.BOTTOM]:
            distance_to_lane = self.get_unit_distance_to_lane(lane, unit)
            if (closest_lane is None) or (distance_to_closest_lane > distance_to_lane):
                closest_lane = lane
                distance_to_closest_lane = distance_to_lane
        if distance_to_closest_lane is not None:
            if distance_to_closest_lane > 400:
                return None
        return closest_lane

    def get_position(self, unit):
        lane = self.get_unit_lane(unit)
        if lane is None:
            return lane, 0
        return lane, self.get_unit_distance_on_lane(lane, unit)

    def get_nexus(self):
        return next(building for building in self.world.buildings
                    if building.type == BuildingType.FACTION_BASE and building.faction == self.me.faction)

    def get_vanguard(self) -> LivingUnit:
        vanguard = self.get_nexus()
        vanguard_distance = 0
        for ally in self.allies():
            lane, distance = self.get_position(ally)
            if lane != self.lane:
                continue
            if distance > vanguard_distance:
                vanguard = ally
                vanguard_distance = distance
        print(self.world.tick_index, "vanguard: %s" % self.unit_to_str(vanguard))
        return vanguard

    def aims_me(self, enemy):
        distance = self.me.get_distance_to_unit(enemy) - self.me.radius
        if distance > self.get_attack_distance(enemy):
            return False
        if enemy.remaining_action_cooldown_ticks > 10:
            return False
        # if type(enemy) is not Wizard:
        #    for ally in self.allies():
        #        distance_to_ally = enemy.get_distance_to_unit(enemy) - ally.radius
        #        if distance_to_ally < distance:
        #            return False
        return True

    def get_closest_attacker(self):
        closest_orc = self.get_closest_orc_attacker()
        if closest_orc is not None:
            return closest_orc
        closest_attacker = None
        closest_attacker_distance = None
        for enemy in self.enemy_units():
            if not self.aims_me(enemy):
                continue
            attacker_distance = self.me.get_distance_to_unit(enemy)
            if (closest_attacker_distance is None) or (closest_attacker_distance > attacker_distance):
                closest_attacker = enemy
                closest_attacker_distance = attacker_distance
        return closest_attacker

    def is_enemy(self, unit):
        if unit.faction == self.me.faction:
            return False
        if unit.faction == Faction.NEUTRAL:
            if unit.id in self.angry_neutrals:
                return True
            if type(unit) is not Minion:
                return False
            is_angry = (unit.life < unit.max_life) or (unit.remaining_action_cooldown_ticks > 0)
            if is_angry:
                self.angry_neutrals.add(unit.id)
            return is_angry
        return True

    def get_closest_orc_attacker(self):
        closest_attacker = None
        closest_attacker_life = None
        for attacker in self.world.minions:
            if not self.is_enemy(attacker):
                continue
            if attacker.type != MinionType.ORC_WOODCUTTER:
                continue
            distance = self.me.get_distance_to_unit(attacker) - self.me.radius
            attack_distance = self.get_attack_distance(attacker)
            if attack_distance < distance:
                continue
            print(self.world.tick_index, "Attacker: %s" % self.unit_to_str(attacker))
            if (closest_attacker is None) or attacker.life < closest_attacker_life:
                closest_attacker = attacker
                closest_attacker_life = attacker.life
        return closest_attacker

    def get_closest_wizard_attacker(self):
        closest_wizard = None
        closest_wizard_distance = None
        for wizard in self.world.wizards:
            if wizard.faction == self.me.faction:
                continue
            distance = self.me.get_distance_to_unit(wizard) - self.me.radius
            if distance > self.me.cast_range:
                continue
            print(self.world.tick_index, "Hazard: %s" % self.unit_to_str(wizard))
            if (closest_wizard is None) or distance < closest_wizard_distance:
                closest_wizard = wizard
                closest_wizard_distance = distance
        return closest_wizard

    def enemy_units(self):
        targets = self.world.buildings + self.world.wizards + self.world.minions
        return [unit for unit in targets if self.is_enemy(unit)]

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
        random.seed(game.random_seed)
        map_size = game.map_size
        self.waypoints_by_lane = {
            LaneType.MIDDLE: [
                Point2D(100.0, map_size - 100.0),
                random.choice([Point2D(600.0, map_size - 200.0), Point2D(200.0, map_size - 600.0)]),
                Point2D(800.0, map_size - 800.0),
                Point2D(map_size - 1000.0, 1000.0)
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
                Point2D(map_size * 0.725, 100.0),
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
                Point2D(map_size - 100.0, map_size * 0.275),
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

        # self.lane = LaneType.MIDDLE
        self.waypoints = self.waypoints_by_lane[self.lane]

    def get_attack_distance(self, unit):
        if type(unit) is Wizard:
            return unit.cast_range
        elif type(unit) is Building:
            return unit.attack_range
        elif type(unit) is Minion:
            if unit.type == MinionType.ORC_WOODCUTTER:
                return self.game.orc_woodcutter_attack_range * 2
            elif unit.type == MinionType.FETISH_BLOWDART:
                return self.game.fetish_blowdart_attack_range
        else:
            print(self.world.tick_index, "Unknown enemy", unit)
            return 0

    def go_to_next_waypoint(self):
        if self.me.get_distance_to_unit(self.waypoints[-1]) < WAYPOINT_RADIUS:
            return
        next_waypoint = self.get_next_waypoint()
        if next_waypoint is None:
            return
        if next_waypoint != self.last_waypoint:
            self.last_waypoint = next_waypoint
            print(self.world.tick_index, "Go to next waypoint")
        self.go_to_waypoint(next_waypoint)

    def get_next_point(self):
        dx = math.cos(self.me.angle)
        dy = math.sin(self.me.angle)
        dx *= (self.game.wizard_cast_range * 0.9)
        dy *= (self.game.wizard_cast_range * 0.9)
        return Point2D(self.me.x + dx, self.me.y + dy)

    def get_sub_waypoint(self, waypoint):
        dx = waypoint.x - self.me.x
        dy = waypoint.y - self.me.y
        l = math.hypot(dx, dy)
        dx *= (self.game.staff_range * 0.5 / l)
        dy *= (self.game.staff_range * 0.5 / l)
        return Point2D(self.me.x + dx, self.me.y + dy)

    def get_closest_obstacle(self, waypoint):
        src = Point2D(self.me.x, self.me.y)
        dst1 = self.get_next_point()
        dst2 = self.get_sub_waypoint(waypoint)
        closest_obstacle = None
        distance_to_closest_obstacle = None
        for obstacle in self.world.trees + self.enemy_units():
            distance1 = distance_to_segment(obstacle, src, dst1)
            if distance1 > self.me.radius + obstacle.radius:
                distance2 = distance_to_segment(obstacle, src, dst2)
                if distance2 > self.me.radius + obstacle.radius:
                    continue
            distance_to_obstacle = self.me.get_distance_to_unit(obstacle)
            if (distance_to_closest_obstacle is None) or (distance_to_obstacle < distance_to_closest_obstacle):
                closest_obstacle = obstacle
                distance_to_closest_obstacle = distance_to_obstacle
        return closest_obstacle

    def is_attack_angle(self, target, shell_radius):
        angle = abs(self.me.get_angle_to_unit(target))
        if angle < self.game.staff_sector / 2.0:
            return True

        if angle > math.pi / 2:
            return False

        dx = target.x - self.me.x
        dy = target.y - self.me.y
        distance = math.hypot(dx, dy)
        dx *= ((shell_radius + self.me.radius) / distance)
        dy *= ((shell_radius + self.me.radius) / distance)

        angle1 = self.me.get_angle_to(target.x - dy, target.y + dx)
        angle2 = self.me.get_angle_to(target.x + dy, target.y - dx)

        target_sector = min(angle1, angle2), max(angle1, angle2)
        attack_sector = -self.game.staff_sector / 2.0, +self.game.staff_sector / 2.0
        return sectors_intersects(target_sector, attack_sector)

    def is_current_attack_angle(self, target):
        angle = self.me.get_angle_to_unit(target)
        return -self.game.staff_sector / 2.0 < angle < +self.game.staff_sector / 2.0

    def can_cast_frost_bolt(self):
        return self.has_frost_bolt and self.me.remaining_cooldown_ticks_by_action[ActionType.FROST_BOLT] == 0

    def setup_attack(self, target):
        angle = self.me.get_angle_to_unit(target)
        self.current_move.turn = angle

        if self.me.remaining_action_cooldown_ticks > 0:
            return

        distance = self.me.get_distance_to_unit(target)
        if distance < self.game.staff_range + target.radius:
            if self.me.remaining_cooldown_ticks_by_action[ActionType.STAFF] == 0:
                if -self.game.staff_sector / 2.0 < angle < +self.game.staff_sector / 2.0:
                    print(self.world.tick_index, "STAFF ATTACK for %s" % self.unit_to_str(target))
                    self.current_move.action = ActionType.STAFF
        if distance < self.me.cast_range + target.radius:
            if self.me.remaining_cooldown_ticks_by_action[ActionType.MAGIC_MISSILE] == 0:
                ticks_to_achieve = math.ceil(distance / self.game.magic_missile_speed)
                future_position = predict_position(target, ticks_to_achieve)
                future_distance = self.me.get_distance_to_unit(future_position) - target.radius
                if self.is_attack_angle(future_position, self.game.magic_missile_radius):
                    print(self.world.tick_index, "MISSILE for %s" % self.unit_to_str(target))
                    self.current_move.cast_angle = self.me.get_angle_to_unit(future_position)
                    self.current_move.min_cast_distance = future_distance + self.game.magic_missile_radius
                    self.current_move.action = ActionType.MAGIC_MISSILE
            if self.can_cast_frost_bolt():
                ticks_to_achieve = math.ceil(self.me.get_distance_to_unit(target) / self.game.frost_bolt_speed)
                future_position = predict_position(target, ticks_to_achieve)
                future_distance = self.me.get_distance_to_unit(future_position) - target.radius
                if self.is_attack_angle(future_position, self.game.frost_bolt_radius):
                    print(self.world.tick_index, "FROST for %s" % self.unit_to_str(target))
                    self.current_move.cast_angle = self.me.get_angle_to_unit(future_position)
                    self.current_move.min_cast_distance = future_distance + self.game.frost_bolt_radius
                    self.current_move.action = ActionType.FROST_BOLT

    def go_to_waypoint(self, waypoint):
        can_move = True
        distance_to_check = self.me.radius * 0.5
        dst = Point2D(
            self.me.x + math.cos(self.me.angle) * distance_to_check,
            self.me.y + math.sin(self.me.angle) * distance_to_check)
        for unit in self.world.buildings + self.world.wizards + self.world.minions:
            if unit.id == self.me.id:
                continue
            if distance_to_segment(unit, self.me, dst) < self.me.radius + unit.radius:
                print(self.world.tick_index, "Cannot move")
                can_move = False
                break
        angle = self.me.get_angle_to(waypoint.x, waypoint.y)
        self.current_move.turn = angle

        if abs(angle) > self.game.staff_sector / 4.0:
            return True

        obstacle = self.get_closest_obstacle(waypoint)
        if obstacle is not None:
            print(self.world.tick_index, "Obstacle: %s" % self.unit_to_str(obstacle))
            self.setup_attack(obstacle)
            self.last_tree = obstacle.id
            self.current_move.speed = self.game.wizard_forward_speed
            self.current_move.strafe_speed = 0
            return True

        if not can_move:
            return False
        self.current_move.speed = self.game.wizard_forward_speed
        self.current_move.strafe_speed = 0
        return True

    def retreat(self):
        previous_waypoint = self.get_previous_waypoint()

        distance_to_check = self.me.radius * 0.5
        x = self.me.x - math.cos(self.me.angle) * distance_to_check
        y = self.me.y - math.sin(self.me.angle) * distance_to_check

        x_locked = (x - self.me.radius < 0) or (x + self.me.radius > self.game.map_size)
        y_locked = (y - self.me.radius < 0) or (y + self.me.radius > self.game.map_size)
        if x_locked or y_locked:
            return False

        for unit in self.world.buildings + self.world.minions + self.world.trees + self.world.wizards:
            if unit.id != self.me.id:
                if distance_to_segment(unit, self.me, Point2D(x, y)) < self.me.radius + unit.radius:
                    return False

        angle = -self.me.get_angle_to(previous_waypoint.x, previous_waypoint.y)
        self.current_move.turn = angle
        self.current_move.speed = -self.game.wizard_backward_speed
        return True

    def pick_bonus_respawn(self):
        bonus_pos1 = self.game.map_size * 0.3
        bonus_pos2 = self.game.map_size * 0.7
        bonus1 = Point2D(bonus_pos1, bonus_pos1)
        bonus2 = Point2D(bonus_pos2, bonus_pos2)
        if self.me.get_distance_to_unit(bonus1) <= self.me.get_distance_to_unit(bonus2):
            return bonus1
        else:
            return bonus2

    def find_closest_bonus(self):
        closest_bonus = None
        closest_bonus_distance = None
        for bonus in self.world.bonuses:
            bonus_distance = self.me.get_distance_to_unit(bonus)
            if bonus_distance > self.me.vision_range:
                continue
            if (closest_bonus_distance is None) or (closest_bonus_distance > bonus_distance):
                closest_bonus_distance = bonus_distance
                closest_bonus = bonus
        if not closest_bonus:
            bonus_ticks = self.game.bonus_appearance_interval_ticks
            ticks = (self.world.tick_index % bonus_ticks)
            if bonus_ticks * 7 / 8 < ticks < bonus_ticks:
                closest_bonus = self.pick_bonus_respawn()
                distance_to_bonus = self.me.get_distance_to_unit(closest_bonus)
                if distance_to_bonus < self.me.vision_range * 0.3:
                    return None
                if (self.world.tick_index > bonus_ticks) and (distance_to_bonus > 1200):
                    return None
        return closest_bonus

    def get_straying_enemy(self):
        closest_straying_enemy = None
        closest_straying_enemy_distance = None
        for enemy in self.enemy_units():
            distance = self.me.get_distance_to_unit(enemy)
            if distance > self.me.vision_range:
                continue
            if type(enemy) in [Minion, Building]:
                return None
            if (closest_straying_enemy is None) or (closest_straying_enemy_distance > distance):
                closest_straying_enemy_distance = distance
                closest_straying_enemy = enemy
        return closest_straying_enemy

    def get_wound_enemy(self):
        closest_wound_enemy = None
        closest_wound_enemy_distance = None
        for wizard in self.world.wizards:
            if wizard.faction == self.me.faction:
                continue
            distance = self.me.get_distance_to_unit(wizard)
            if distance > self.me.vision_range:
                continue
            if wizard.life >= self.me.max_life * LOW_HP_FACTOR:
                continue
            if (closest_wound_enemy is None) or (closest_wound_enemy_distance > distance):
                closest_wound_enemy_distance = distance
                closest_wound_enemy = wizard
        return closest_wound_enemy

    def is_free_way(self, target):
        distance_to_check = self.me.radius * 0.5
        dst = Point2D(
            self.me.x + math.cos(self.me.angle) * distance_to_check,
            self.me.y + math.sin(self.me.angle) * distance_to_check)
        for unit in self.world.buildings + self.world.wizards + self.world.minions + self.world.trees:
            if unit.id in [self.me.id, target.id]:
                continue
            if distance_to_segment(unit, self.me, dst) < self.me.radius + unit.radius:
                print(self.world.tick_index, "Freeway is blocked by %s" % self.unit_to_str(unit))
                return False
        return True

    def shall_retreat_from_attacker(self, attacker: LivingUnit):
        if attacker.life < attacker.max_life * LOW_HP_FACTOR + 6:
            return False
        if type(attacker) is Wizard:
            return True
        attacker_distance = self.me.get_distance_to_unit(attacker)
        return attacker_distance < self.game.score_gain_range * 0.9

    def setup_skills(self):
        if self.me.level == self.last_level:
            return
        next_skill = self.skills_to_learn[self.last_level]
        self.current_move.skill_to_learn = next_skill
        if next_skill == SkillType.ADVANCED_MAGIC_MISSILE:
            self.advanced_missile = True
        elif next_skill == SkillType.FROST_BOLT:
            self.has_frost_bolt = True
        elif next_skill == SkillType.FIREBALL:
            self.has_fireball = True
        elif next_skill == SkillType.HASTE:
            self.has_haste = True
        elif next_skill == SkillType.SHIELD:
            self.has_shield = True
        self.last_level += 1
        print(self.world.tick_index, "LEVEL UP! Level=%d, skill=%d" % (self.me.level, self.current_move.skill_to_learn))

    def move(self, me: Wizard, world: World, game: Game, move: Move):
        self.initialize_tick(me, world, game, move)

        if self.game.skills_enabled:
            self.setup_skills()

        if self.last_tree is not None:
            obstacle = next((tree for tree in self.world.trees if tree.id == self.last_tree), None)
            if obstacle is not None:
                print(self.world.tick_index, "Continue removing the obstacle")
                self.setup_attack(obstacle)
                if abs(self.me.get_angle_to_unit(obstacle)) < self.game.staff_sector / 2:
                    self.current_move.speed = self.game.wizard_forward_speed
                    self.current_move.strafe_speed = 0
                return
            self.last_tree = None

        self.setup_strafe()

        move_forward = True

        if me.life < me.max_life * LOW_HP_FACTOR:
            nearest_target = self.get_nearest_target()
            if nearest_target is not None:
                self.setup_attack(nearest_target)
            if self.retreat():
                print(self.world.tick_index, "Medic!")
                return
            print(self.world.tick_index, "Medic needed, but no chance to retreat")
            move_forward = False
        else:
            bonus = self.find_closest_bonus()
            if bonus is not None:
                print(self.world.tick_index, "Bonus: %s" % self.unit_to_str(bonus))
                self.go_to_waypoint(bonus)
                hazard = self.get_closest_wizard_attacker()
                if hazard and hazard.get_distance_to_unit(bonus) < 800:
                    print(self.world.tick_index, "Hazard: %s" % self.unit_to_str(hazard))
                    self.setup_attack(hazard)
                return

        vanguard = self.get_vanguard()
        if vanguard is not None:
            if self.get_unit_lane(self.me) != self.lane:
                print(self.world.tick_index, "Out of lane, go to vanguard")
                self.go_to_waypoint(vanguard)
                move_forward = False
            else:
                vanguard_distance = self.get_unit_distance_on_lane(self.lane, vanguard)
                my_distance = self.get_unit_distance_on_lane(self.lane, self.me)
                straying_enemy = self.get_straying_enemy()
                if move_forward and (straying_enemy is not None):
                    self.go_to_waypoint(straying_enemy)
                    self.setup_attack(straying_enemy)
                    move_forward = False
                elif my_distance + 30 > vanguard_distance:
                    if my_distance > vanguard_distance + 100:
                        self.go_to_waypoint(vanguard)
                    else:
                        if self.retreat():
                            print(self.world.tick_index, "There is no vanguard. Retreat.")
                        else:
                            print(self.world.tick_index, "There is no vanguard. Cannot retreat")
                    move_forward = False

        closest_attacker = self.get_closest_attacker()
        if closest_attacker is not None:
            print(self.world.tick_index, "Under attack! %s" % self.unit_to_str(closest_attacker))
            if self.shall_retreat_from_attacker(closest_attacker):
                if self.retreat():
                    print(self.world.tick_index, "Retreat")
                else:
                    print(self.world.tick_index, "Failed to retreat")
                move_forward = False
            else:
                print(self.world.tick_index, "Should not retreat")
        else:
            print(self.world.tick_index, "There is no attacker")

        nearest_target = self.get_nearest_target()
        if nearest_target is not None:
            self.setup_attack(nearest_target)
            # if move_forward and self.current_move.action != ActionType.NONE:
            #    self.current_move.speed = self.game.wizard_forward_speed
            return

        print(self.world.tick_index, "No target to attack")

        if move_forward:
            self.go_to_next_waypoint()
