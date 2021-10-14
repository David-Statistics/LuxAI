import math, sys
from lux.game import Game
from lux.game_map import Cell, RESOURCE_TYPES
from lux.constants import Constants
from lux.game_constants import GAME_CONSTANTS
from lux import annotate

DIRECTIONS = Constants.DIRECTIONS
game_state = None
TAKEN_TARGETS = []

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

def get_map_values(m, p):
    width, height = m.width, m.height
    d = {}
    for y in range(height):
        for x in range(width):
            adj = get_adjacent_cells(m.get_cell(x,y), m)
            adj.append(m.get_cell(x,y))
            d[(x,y)] = sum([get_cell_value(cell, p) for cell in adj])
    return d

def cities_powered(p):
    status = True
    for k, city in p.cities.items():
        if city.fuel < math.ceil(city.get_light_upkeep() + 180):
            status = False 
            break
    return status

def is_empty(c):
    if c.has_resource():
        return False
    if c.citytile is None:
        return True
    return False

def get_expansion_sites(city, m):
    borders_dup: list[Cell] = []
    for ct in city.citytiles:
        borders_dup.append(get_adjacent_cells(ct, m))
    if type(borders_dup[0]) is list:
        borders_dup = [c for sublist in borders_dup for c in sublist]
    borders = [c for c in set(borders_dup) if is_empty(c)]
    return borders
    
def build(u, p, m):
    target_loc = None
    target_dist = math.inf
    for k, city in p.cities.items():
        expansions = get_expansion_sites(city, m)
        expansions = [x for x in expansions if x not in TAKEN_TARGETS]
        if len(expansions) > 0:
            if u.pos in [c.pos for c in expansions]:
                return u.build_city() 
            else:
                for site in expansions:
                    dist = site.pos.distance_to(u.pos)
                    if dist < target_dist:
                        target_dist = dist
                        target_loc = site
            if target_dist > 5 and u.can_build(m):
                return u.build_city() 
    TAKEN_TARGETS.append(target_loc)
    return u.move(u.pos.direction_to(target_loc.pos))

def gather(u, p, m, resource_tiles):
    best_val = 0
    best_tile = None
    values = get_map_values(m, p)
    resource_tiles = [x for x in resource_tiles if x not in TAKEN_TARGETS]
    for resource_tile in resource_tiles:
        dist = resource_tile.pos.distance_to(u.pos)
        if dist < 15:
            val = values[(resource_tile.pos.x, resource_tile.pos.y)] / (math.log(dist + 2))
            if val > best_val:
                best_val = val
                best_tile = resource_tile
    TAKEN_TARGETS.append(best_tile)
    return u.move(u.pos.direction_to(best_tile.pos))

def return_home(u, p, m):
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
    move_dir = u.pos.direction_to(closest_city_tile.pos)
    return u.move(move_dir)

def agent(observation, configuration):
    global game_state

    ### Do not edit ###
    if observation["step"] == 0:
        game_state = Game()
        game_state._initialize(observation["updates"])
        game_state._update(observation["updates"][2:])
        game_state.id = observation.player
    else:
        game_state._update(observation["updates"])
    
    actions = []
    targets = []

    ### AI Code goes down here! ### 
    player = game_state.players[observation.player]
    opponent = game_state.players[(observation.player + 1) % 2]
    width, height = game_state.map.width, game_state.map.height

    resource_tiles = get_resource_cells(game_state.map)

    # we iterate over all our units and do something with them
    for unit in player.units:
        day_cycle = game_state.turn % 40
        threshold = 0
        if unit.is_worker():
            if day_cycle > 27:
                threshold = 4 * min(10, 40 - day_cycle)
            if unit.cargo.wood < threshold:
                actions.append(return_home(unit, player, game_state.map))
            elif not unit.can_act():
                continue
            elif unit.get_cargo_space_left() > 0:
                actions.append(gather(unit, player, game_state.map, resource_tiles))
            elif cities_powered(player):
                actions.append(build(unit, player, game_state.map))   
            else:
                actions.append(return_home(unit, player, game_state.map))

    can_build = player.city_tile_count - len(player.units)
    if len(player.units) > 3:
        can_build = math.ceil(1.0 * player.city_tile_count * .67) - len(player.units)
    for k, city in player.cities.items():
        for ct in city.citytiles:
            if ct.can_act():
                if can_build > 0:
                    actions.append(ct.build_worker())
                else:
                    actions.append(ct.research())
            

    # you can add debug annotations using the functions in the annotate object
    # actions.append(annotate.circle(0, 0))
    actions = [x for x in actions if x is not None]
    return actions
