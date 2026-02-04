"""Server-side Tetris engine for game state validation and reconciliation."""

import hashlib
import json
from typing import List, Dict, Optional, Tuple
from .prng import SeededRandom


# Game constants matching client
COLS = 10
ROWS = 15
COLORS = ['cyan', 'blue', 'orange', 'yellow', 'green', 'purple', 'red']

BLOCK_SHAPES = [
    {'blocks': [[-1, 0], [0, 0], [1, 0], [2, 0]], 'center': [0, 0]},      # I
    {'blocks': [[-1, 0], [0, 0], [1, 0], [1, -1]], 'center': [0, 0]},     # J
    {'blocks': [[-1, 0], [0, 0], [1, 0], [1, 1]], 'center': [0, 0]},      # L
    {'blocks': [[0, 0], [1, 0], [0, 1], [1, 1]], 'center': None},         # O
    {'blocks': [[-1, 0], [0, 0], [0, 1], [1, 1]], 'center': [0, 0]},      # S
    {'blocks': [[-1, 0], [0, 0], [1, 0], [0, 1]], 'center': [0, 0]},      # T
    {'blocks': [[-1, 1], [0, 1], [0, 0], [1, 0]], 'center': [0, 0]}       # Z
]


class TetrisEngine:
    """Server-side Tetris game engine for validation."""

    def __init__(self, seed: int):
        self.rng = SeededRandom(seed)
        self.grid: List[List[int]] = [[0] * COLS for _ in range(ROWS)]
        self.score = 0
        self.current_block = None
        self.game_over = False
        self.last_seq = 0

        # Generate first block
        self.current_block = self._generate_block()

    def _generate_block(self) -> Dict:
        """Generate a new block using seeded random."""
        index = self.rng.next_int(len(BLOCK_SHAPES))
        shape = BLOCK_SHAPES[index]
        blocks = [list(b) for b in shape['blocks']]
        center = list(shape['center']) if shape['center'] else None
        color = COLORS[index]

        min_dy = min(b[1] for b in blocks)

        block = {
            'x': 4,
            'y': -min_dy,
            'color': color,
            'blocks': blocks,
            'center': center,
            'color_index': index
        }

        if self._is_colliding(block, block['x'], block['y']):
            self.game_over = True

        return block

    def _is_colliding(self, block: Dict, offset_x: int, offset_y: int,
                      override: List = None, strict: bool = False) -> bool:
        """Check if block collides with grid or boundaries."""
        cells = override if override else block['blocks']

        for dx, dy in cells:
            x = offset_x + dx
            y = offset_y + dy

            if x < 0 or x >= COLS or y >= ROWS:
                return True
            if strict and y < 0:
                return True
            if y >= 0 and self.grid[y][x] != 0:
                return True

        return False

    def _place_block(self) -> int:
        """Place current block on grid and return lines cleared."""
        block = self.current_block
        color_index = block['color_index'] + 1

        for dx, dy in block['blocks']:
            x = block['x'] + dx
            y = block['y'] + dy
            if y >= 0:
                self.grid[y][x] = color_index

        return self._clear_lines()

    def _clear_lines(self) -> int:
        """Clear completed lines and return count."""
        cleared = 0
        y = ROWS - 1

        while y >= 0:
            if all(cell != 0 for cell in self.grid[y]):
                self.grid.pop(y)
                self.grid.insert(0, [0] * COLS)
                cleared += 1
            else:
                y -= 1

        return cleared

    def _add_score(self, lines: int, is_hard_drop: bool = False):
        """Calculate and add score based on lines cleared."""
        if lines == 1:
            base = 100
        elif lines == 2:
            base = 300
        elif lines == 3:
            base = 500
        elif lines >= 4:
            base = 800
        else:
            base = 0

        gained = base * 2 if is_hard_drop else base
        self.score += gained

    def apply_input(self, action: str, seq: int) -> Dict:
        """Apply an input action and return result."""
        if self.game_over:
            return {'valid': False, 'reason': 'game_over'}

        if seq <= self.last_seq:
            return {'valid': False, 'reason': 'stale_sequence'}

        self.last_seq = seq
        result = {'valid': True, 'action': action, 'seq': seq}

        if action == 'left':
            self._move(-1, 0)
        elif action == 'right':
            self._move(1, 0)
        elif action == 'down':
            self._move(0, 1)
        elif action == 'rotate':
            self._rotate()
        elif action == 'hardDrop':
            self._hard_drop()
        else:
            result['valid'] = False
            result['reason'] = 'unknown_action'

        result['score'] = self.score
        result['state_hash'] = self.get_state_hash()
        result['game_over'] = self.game_over

        return result

    def _move(self, dx: int, dy: int):
        """Move current block."""
        if self.game_over or not self.current_block:
            return

        block = self.current_block
        new_x = block['x'] + dx
        new_y = block['y'] + dy

        if not self._is_colliding(block, new_x, new_y):
            block['x'] = new_x
            block['y'] = new_y
        elif dy == 1:
            lines = self._place_block()
            self._add_score(lines)
            self.current_block = self._generate_block()

    def _rotate(self):
        """Rotate current block."""
        if self.game_over or not self.current_block:
            return

        block = self.current_block
        if not block['center']:
            return

        cx, cy = block['center']
        rotated = []
        for x, y in block['blocks']:
            rel_x = x - cx
            rel_y = y - cy
            rotated.append([-rel_y + cx, rel_x + cy])

        if not self._is_colliding(block, block['x'], block['y'], rotated, strict=True):
            block['blocks'] = rotated

    def _hard_drop(self):
        """Hard drop current block."""
        if self.game_over or not self.current_block:
            return

        block = self.current_block
        while not self._is_colliding(block, block['x'], block['y'] + 1):
            block['y'] += 1

        lines = self._place_block()
        self._add_score(lines, is_hard_drop=True)
        self.current_block = self._generate_block()

    def tick(self):
        """Execute one game tick (automatic drop)."""
        if not self.game_over:
            self._move(0, 1)

    def get_state_hash(self) -> str:
        """Generate a hash of current game state for synchronization check."""
        state = {
            'grid': self.grid,
            'score': self.score,
            'current': {
                'x': self.current_block['x'] if self.current_block else 0,
                'y': self.current_block['y'] if self.current_block else 0,
                'blocks': self.current_block['blocks'] if self.current_block else [],
                'color_index': self.current_block['color_index'] if self.current_block else 0
            } if self.current_block else None,
            'game_over': self.game_over
        }

        state_str = json.dumps(state, sort_keys=True)
        return hashlib.md5(state_str.encode()).hexdigest()[:16]

    def get_full_state(self) -> Dict:
        """Get full game state for client synchronization."""
        return {
            'grid': self.grid,
            'score': self.score,
            'current_block': self.current_block,
            'game_over': self.game_over,
            'state_hash': self.get_state_hash()
        }
