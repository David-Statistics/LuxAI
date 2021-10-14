import math, sys
from lux import game
from lux.game import Game
from lux.game_map import Cell, RESOURCE_TYPES
from lux.constants import Constants
from lux.game_constants import GAME_CONSTANTS
from lux import annotate
import logging

logging.basicConfig(filename='agent.log', level=logging.INFO)

DIRECTIONS = Constants.DIRECTIONS
game_state = None
TARGET_LOCS = {}
UNIT_LOCATIONS = {}
EXPLORER = []


def get_resource_cells(m):
    width, height = m.width, m.height
    resource_tiles: list[Cell] = []
    for y in range(height):
        for x in range(width):
            cell = m.get_cell(x, y)
            if cell.has_resource():
                resource_tiles.append(cell)
    return resource_tiles

def get_adjacent_cells(cell, m):
    adj_cells: list[Cell] = []
    x, y = cell.pos.x, cell.pos.y
    if x > 0:
        adj_cells.append(m.get_cell(x-1,y))
    if x < (m.width-1):
        adj_cells.append(m.get_cell(x+1,y))
    if y > 0:
        adj_cells.append(m.get_cell(x,y-1))
    if y < (m.width-1):
        adj_cells.append(m.get_cell(x,y+1))
    return adj_cells

def get_cell_value(cell, p):
    if not cell.has_resource():
        return 0
    if cell.resource.type == Constants.RESOURCE_TYPES.COAL:
        if not p.researched_coal():
            return 0
        else:
            return 50
    if cell.resource.type == Constants.RESOURCE_TYPES.URANIUM:
        if not p.researched_uranium():
            return 0
        else:
            return 80
    return 20

def get_energy(unit):
    return unit.cargo.wood + unit.cargo.coal * 10 + unit.cargo.uranium * 40

def get_map_values(m, p):
    width, height = m.width, m.height
    d = {}
    for y in range(height):
        for x in range(width):
            adj = get_adjacent_cells(m.get_cell(x,y), m)
            adj.append(m.get_cell(x,y))
            d[(x,y)] = sum([get_cell_value(cell, p) for cell in adj])
    return d

def cities_powered(p, day_cycle):
    status = True
    for k, city in p.cities.items():
        if day_cycle > 20:
            if city.fuel < math.ceil(city.get_light_upkeep()*8 + 180):
                status = False 
                break
        elif day_cycle > 10:
            if city.fuel < math.ceil((city.get_light_upkeep()*3)):
                status = False 
                break
    return status

def is_empty(c):
    if c.has_resource():
        return False
    if c.citytile is None:
        return True
    return False

def get_coords(c):
    return (c.pos.x, c.pos.y)

def get_expansion_sites(city, m):
    borders_dup: list[Cell] = []
    for ct in city.citytiles:
        borders_dup.append(get_adjacent_cells(ct, m))
    if type(borders_dup[0]) is list:
        borders_dup = [c for sublist in borders_dup for c in sublist]
    borders = [c for c in set(borders_dup) if is_empty(c)]
    return borders

def take_step(u, target, m, allow_city, opp_locs, my_cities):
    global UNIT_LOCATIONS
    target = m.get_cell(target[0], target[1])
    
    if u.pos == target.pos:
        return None
    occ_loc = [UNIT_LOCATIONS[id] for id in UNIT_LOCATIONS.keys()]
    occ_loc = [coord for coord in occ_loc if m.get_cell(coord[0], coord[1]).citytile is None]
    occ_loc = occ_loc + opp_locs
    if not allow_city:
        occ_loc = occ_loc + my_cities
    if u.pos.y > target.pos.y:
        if (u.pos.x, u.pos.y - 1) not in occ_loc:
            UNIT_LOCATIONS[u.id] = (u.pos.x, u.pos.y - 1)
            return u.move(DIRECTIONS.NORTH)
    elif u.pos.y < target.pos.y:
        if (u.pos.x, u.pos.y + 1) not in occ_loc:
            UNIT_LOCATIONS[u.id] = (u.pos.x, u.pos.y + 1)
            return u.move(DIRECTIONS.SOUTH)
    if u.pos.x > target.pos.x:
        if (u.pos.x - 1, u.pos.y) not in occ_loc:
            UNIT_LOCATIONS[u.id] = (u.pos.x - 1, u.pos.y)
            return u.move(DIRECTIONS.WEST)
            
    if u.pos.x < target.pos.x:
        if (u.pos.x + 1, u.pos.y) not in occ_loc:
            UNIT_LOCATIONS[u.id] = (u.pos.x + 1, u.pos.y)
            return u.move(DIRECTIONS.EAST)
    return None

def get_gather_target(u, p, m, resource_tiles, allow_city, values):
    best_val = 0.0
    best_tile = None
    taken_targets = [TARGET_LOCS[id] for id in TARGET_LOCS.keys() if id != u.id]
    for tile in values.keys():
        if tile in taken_targets:
            continue
        if not allow_city:
            if m.get_cell(tile[0], tile[1]).citytile is not None:
                continue
        dist = abs(u.pos.x - tile[0]) + abs(u.pos.y - tile[1])
        if dist < 15:
            val = 1.0 * values[tile] / math.log(dist + 2)
            if val > best_val:
                best_val = val
                best_tile = m.get_cell(tile[0], tile[1])
    if best_tile is not None:
        return get_coords(best_tile)
    return None

def find_home(u, p, m):
    if m.get_cell_by_pos(u.pos).citytile is not None:
        return None
    closest_dist = math.inf
    closest_city_tile = None
    for k, city in p.cities.items():
        for city_tile in city.citytiles:
            dist = city_tile.pos.distance_to(u.pos)
            if dist < closest_dist:
                closest_dist = dist
                closest_city_tile = city_tile
    if closest_city_tile is not None:
        return get_coords(closest_city_tile)
    return None

def get_closest_dist(coord, p, m):
    closest_dist = math.inf
    for k, city in p.cities.items():
        for city_tile in city.citytiles:
            dist = abs(coord[0] - city_tile.pos.x) + abs(coord[1] - city_tile.pos.y)
            if dist < closest_dist:
                closest_dist = dist
    return closest_dist

def get_city_dists(p, m):
    dists = {}
    for x in range(m.width):
        for y in range(m.height):
            c = m.get_cell(x, y)
            if c.has_resource() or c.citytile is not None:
                dists[(x,y)] = 0
            elif x < 3 or y < 3 or x > (m.width - 4) or y > (m.height - 4):
                dists[(x,y)] = 0
            else:
                dists[(x,y)] = get_closest_dist((x,y), p, m)
    return dists


def get_build_loc(u, p, m, new_city, opponent):
    global EXPLORER
    target_loc = None
    target_dist = math.inf
    if new_city:
        dists = get_city_dists(p, m)
        ranks = sorted([(dists[coord], coord) for coord in dists.keys()], key=lambda x: (-x[0], x[1][0], x[1][1]))
        if get_coords(u) == ranks[0][1]:
            EXPLORER = [x for x in EXPLORER if x != u.id]
            return u.build_city()
        if ranks[0][1] is not None:
            return ranks[0][1]
    if p.city_tile_count == 0:
        if is_empty(m.get_cell_by_pos(u.pos)):
            return u.build_city()
        else:
            adj = get_adjacent_cells(m.get_cell_by_pos(u.pos), m)
            adj = [x for x in adj if is_empty(x)]
            if len(adj) > 0:
                return u.move(u.pos.direction_to(adj[0].pos))
            else:
                return u.move(DIRECTIONS.SOUTH)
    for k, city in p.cities.items():
        expansions = get_expansion_sites(city, m)
        taken_targets = [TARGET_LOCS[id] for id in TARGET_LOCS.keys() if id != u.id]
        expansions = [x for x in expansions if get_coords(x) not in taken_targets]
        if len(expansions) > 0:
            if u.pos in [c.pos for c in expansions]:
                return u.build_city() 
            else:
                for site in expansions:
                    dist = site.pos.distance_to(u.pos)
                    if dist < target_dist:
                        target_dist = dist
                        target_loc = site
                    elif dist == target_dist:
                        if site.pos.x != u.pos.x and site.pos.y != u.pos.y:
                            target_loc = site
    if target_dist > 3 and u.can_build(m):
        return u.build_city()      
    if target_loc is not None: 
        return get_coords(target_loc)
    return None

def agent(observation, configuration):
    global TARGET_LOCS
    global UNIT_LOCATIONS
    global game_state
    global EXPLORER

    ### Do not edit ###
    if observation["step"] == 0:
        game_state = Game()
        game_state._initialize(observation["updates"])
        game_state._update(observation["updates"][2:])
        game_state.id = observation.player
    else:
        game_state._update(observation["updates"])

    starting_locs = {}
    
    actions = []

    ### AI Code goes down here! ### 
    player = game_state.players[observation.player]
    opponent = game_state.players[(observation.player + 1) % 2]
    width, height = game_state.map.width, game_state.map.height

    resource_tiles = get_resource_cells(game_state.map)
    unit_count = len(player.units)
    city_count = len(player.cities.items())
    map_values = get_map_values(game_state.map, player)
    day_cycle = game_state.turn % 40
    allow_cities = {}
    ids_to_skip = []
    to_build = []
    any_exploring = False
    total_upkeep = 0
    total_fuel = 0
    for k, city in player.cities.items():
        total_upkeep += city.get_light_upkeep()
        total_fuel += city.fuel

    # we iterate over all our units and do something with them
    for unit in player.units:
        UNIT_LOCATIONS[unit.id] = (unit.pos.x, unit.pos.y)
        starting_locs[unit.id] = (unit.pos.x, unit.pos.y)
        allow_cities[unit.id] = True
        threshold = 0
        target = None
        allow_city = True
        if unit.is_worker():
            if player.city_tile_count == 0:
                if unit.get_cargo_space_left() == 0:
                    target = get_build_loc(unit, player, game_state.map, False, opponent) 
                    to_build.append(unit.id)
                else:
                    target = get_gather_target(unit, player, game_state.map, resource_tiles, False, map_values)
            elif day_cycle >= 30 and game_state.map.get_cell_by_pos(unit.pos).citytile is not None:
                continue
            elif not unit.can_act():
                continue
            elif (get_energy(unit) > 400 and day_cycle > 20) and (total_upkeep * 10) > total_fuel:
                target = find_home(unit, player, game_state.map)
            elif unit.get_cargo_space_left() > 0 and (unit.get_cargo_space_left() >= 40 or day_cycle < 30):
                if unit_count > 2 or not cities_powered(player, day_cycle):
                    target = get_gather_target(unit, player, game_state.map, resource_tiles, True, map_values)
                else:
                    target = get_gather_target(unit, player, game_state.map, resource_tiles, False, map_values)
            elif unit.get_cargo_space_left() == 0 and (cities_powered(player, day_cycle)) and len(to_build) < 4:
                if city_count < math.floor(1.0 * unit_count / (4 * city_count)) and not any_exploring and (len(EXPLORER) == 0 or unit.id in EXPLORER):
                    logging.info(f"trying to explore with {unit.id}")
                    target = get_build_loc(unit, player, game_state.map, True, opponent) 
                    any_exploring = True
                    if unit.id not in EXPLORER:
                        EXPLORER.append(unit.id)
                else:
                    target = get_build_loc(unit, player, game_state.map, False, opponent)
                to_build.append(unit.id)
            else:
                target = find_home(unit, player, game_state.map)
            if type(target) != str and target is not None:
                TARGET_LOCS[unit.id] = target
            else:
                actions.append(target)
                ids_to_skip.append(unit.id)
    
    logging.info(f"TURN: {game_state.turn}; explorer: {EXPLORER}")
    opp_cities = []
    for k, city in opponent.cities.items():
        for ct in city.citytiles:
            opp_cities.append(get_coords(ct))
    my_cities = []
    for k, city in player.cities.items():
        for ct in city.citytiles:
            my_cities.append(get_coords(ct))
    moves_happened = True
    while moves_happened:
        moves_happened = False
        to_iter = [x for x in player.units if x.id not in ids_to_skip]
        for unit in to_iter:
            if unit.can_act():
                if starting_locs[unit.id][0] == UNIT_LOCATIONS[unit.id][0] and starting_locs[unit.id][1] == UNIT_LOCATIONS[unit.id][1]:
                    if unit.id in TARGET_LOCS.keys():
                        if unit.id in to_build:
                            move_cmd = take_step(unit, TARGET_LOCS[unit.id], game_state.map, False, opp_cities, my_cities)
                        else:
                            move_cmd = take_step(unit, TARGET_LOCS[unit.id], game_state.map, True, opp_cities, my_cities)
                        if move_cmd is not None:
                            actions.append(move_cmd)
                            moves_happened = True

    can_build = player.city_tile_count - unit_count
    for k, city in player.cities.items():
        for ct in city.citytiles:
            if ct.can_act():
                if can_build > 0:
                    actions.append(ct.build_worker())
                    can_build = can_build - 1
                else:
                    actions.append(ct.research())
            

    # you can add debug annotations using the functions in the annotate object
    # actions.append(annotate.circle(0, 0))
    actions = [x for x in actions if x is not None]
    #logging.info(f"\n\n")
    #logging.info(f"turn {game_state.turn}: locations {[(id, UNIT_LOCATIONS[id]) for id in UNIT_LOCATIONS.keys()]}")
    return actions