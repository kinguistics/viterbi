try:
    '''numpy's log provides more float precision'''
    from numpy import log
except ImportError:
    from math import log

LOG_SCALED = True

DEFAULT_GOOD_SCORE = 1
DEFAULT_BAD_SCORE = 0.5
DEFAULT_SCORE_COMBINATION = lambda x,y: x*y

if LOG_SCALED:
    DEFAULT_GOOD_SCORE = log(DEFAULT_GOOD_SCORE)
    DEFAULT_BAD_SCORE = log(DEFAULT_BAD_SCORE)
    DEFAULT_SCORE_COMBINATION = lambda x,y: x+y


class ViterbiCell(object):
    """
    The basic element of a Viterbi grid.
    It has a grid position, and elements corresponding to the A and B sequences
    of the parent.

    :param row_idx: the grid row that this cell is in
    :type row_idx: int
    :param col_idx: the grid column that this cell is in
    :type col_idx: int
    :param parent: the parent grid of this cell
    :type parent: ViterbiAligner
    """
    def __init__(self, row_idx, col_idx, parent):
        self.row_idx = row_idx
        self.col_idx = col_idx
        self.parent = parent

        # the current element on each dimension
        try: self.a_element = self.parent.a[row_idx]
        except IndexError: self.a_element = None
        try: self.b_element = self.parent.b[col_idx]
        except IndexError: self.b_element = None

        # the paths that end in this cell
        self.paths = []

    ### TRIVIAL ACCESSORS ###
    def get_row_idx(self):
        return self.row_idx
    def get_col_idx(self):
        return self.col_idx
    def get_a_element(self):
        return self.a_element
    def get_b_element(self):
        return self.b_element

    def get_coordinates(self):
        """returns a tuple (row index, column index)"""
        return (self.get_row_idx(), self.get_col_idx())

    def get_elements(self):
        """returns a tuple (A element, B element)"""
        return (self.a_element, self.b_element)

    def get_name(self):
        """returns a tuple containing the remaining elements of (A,B)"""

        return (self.parent.a[self.row_idx:],
                self.parent.b[self.col_idx:])

    def get_all_paths(self):
        """returns all paths that end in this cell"""
        return self.paths

    def get_best_paths(self):
        """
        Returns a list of paths ending in this cell with the best score.

        If ViterbiCell.parent.scores_are_costs is False, then scores are
        interpreted as probabilities, and the highest-score paths are returned.

        If ViterbiCell.parent.scores_are_costs is True, then scores are
        interpreted as costs, and the lowest-score paths are returned.
        """
        if not len(self.paths):
            return []

        if self.parent.scores_are_costs:
            self.paths.sort(cmp=lambda x,y: cmp(x.score, y.score))
        else:
            self.paths.sort(cmp=lambda x,y: cmp(x.score, y.score), reverse=True)

        # search through to find all paths with the best score
        best_score = self.paths[0].get_score()

        path_idx = 1
        while True:
            try:
                this_path_score = self.paths[path_idx].get_score()
            except IndexError:
                break
            if this_path_score != best_score:
                break
            path_idx += 1

        return self.paths[:path_idx]


class ViterbiPath(object):
    """
    A path through a Viterbi grid (basically a list of cells).
    Always contains the start cell (grid position (0,0))
        and the end cell (grid position (len(a)+1, len(b)+1)

    :param cells: the cells that this path passes through
    :type row_idx: list(ViterbiCell)
    :param score: the score (e.g., probability) of this path
    :type col_idx: float
    """
    def __init__(self, cells, score):
        self.cells = cells
        self.score = score

    def get_score(self):
        return self.score

    def _get_cell_properties(self, what):
        """this method can probably just be moved into get_path_coordinates"""
        path = []
        for cell in self.cells:
            if what == 'elements':
                path.append(cell.get_elements())
            else:
                path.append(cell.get_coordinates())
        return path

    def get_coordinates(self):
        return self._get_cell_properties('coordinates')

    def get_elements(self):
        """
        Returns the aligned elements of the path.

        Return value is of type list(tuple(type(A), type(B))), where A and B
            are the sequences that have been aligned

        Note that len(get_path_elements) == len(get_path_coordinates) - 1
            This is because a path element represents an edge transition between
            two coordinates
        """
        alignment = []

        for cell_idx in range(len(self.cells))[:-1]:
            this_cell = self.cells[cell_idx]
            next_cell = self.cells[cell_idx+1]

            # initialize to None
            a_element = None
            b_element = None

            this_row, this_col = this_cell.get_coordinates()
            next_row, next_col = next_cell.get_coordinates()

            if this_row != next_row:
                a_element = this_cell.get_a_element()
            if this_col != next_col:
                b_element = this_cell.get_b_element()

            alignment.append((a_element, b_element))

        return alignment


class ViterbiAligner(object):
    """
    A ViterbiAligner calculates an alignment between two sequences A and B,
    based on element-wise alignment scores.

    The sequences A and B can be strings or lists of strings (or a combination
    of both). We currently do not support sequences of arbitrary elements.

    The alignment score items {key: value} represents the score (e.g.,
    probability or cost) of aligning the elements (key,value), where key is an
    element from the alphabet of sequence A, and value is an element from the
    alphabet of sequence B.

    The alignment score dictionary can be None, in which case the default
    scores (1 for all (element, element) alignments, 0.5 for alignments
    including a null element) will be used.

    The alignment score dictionary, if provided, should include null elements for
    both keys and values, to represent insertions and deletions, respectively.

    :param a: the "from" sequence to be aligned
    :type a: sequence
    :param b: the "to" sequence to be aligned
    :type b: sequence
    :param alignment_scores: the alignment scores, as described in detail above
    :type alignment_scores: dict or None
    :param scores_are_costs: whether lower scores are better (in contrast with,
        e.g., probabilities, in which higher scores are better)
    :type scores_are_costs: bool
    :param run: whether or not to immediate initialize and run the alignment
    :type run: bool
    """
    def __init__(self, a, b, alignment_scores=None, scores_are_costs=False, run=True):
        self.a = a
        self.b = b
        self.alignment_scores = alignment_scores
        self.scores_are_costs = scores_are_costs

        if run:
            self.initialize_grid()
            self.align()

    def initialize_grid(self):
        grid = []

        # NOTE : we go from index 0 to len(seq)+1
        #  to represent having eaten the final element of seq
        for row_idx in range(len(self.a)+1):
            row = []

            for col_idx in range(len(self.b)+1):
                cell = ViterbiCell(row_idx, col_idx, self)
                row.append(cell)

            grid.append(row)

        self.grid = grid

    def align(self):
        # initialize the first cell to have an empty path, so we have something
        #   to append to at each of its neighbors
        startcell = self.grid[0][0]
        startpath = ViterbiPath([startcell], DEFAULT_GOOD_SCORE)
        startcell.paths.append(startpath)

        for row_idx in range(len(self.grid)):
            row = self.grid[row_idx]
            for col_idx in range(len(row)):
                cell = row[col_idx]
                cell_a_element = cell.get_a_element()
                cell_b_element = cell.get_b_element()

                # DOUBLE CHECK THE EDGE CASES

                # check the deletion (eat element from a, none from b)
                try:
                    delete_cell = self.grid[row_idx+1][col_idx]
                except IndexError: delete_cell = None

                # check the diagonal (eat element from both a and b)
                try:
                    diag_cell = self.grid[row_idx+1][col_idx+1]
                except IndexError: diag_cell = None

                # check the insertion (eat element from b, not a)
                try:
                    insert_cell = self.grid[row_idx][col_idx+1]
                except IndexError: insert_cell = None

                # iterate through all current paths,
                #  and append all available next cells
                for path in cell.paths:
                    for next_cell in [delete_cell, diag_cell, insert_cell]:
                        if next_cell is None:
                            continue

                        # initialize
                        a_next_element = None
                        b_next_element = None
                        move_score = DEFAULT_BAD_SCORE

                        if next_cell == diag_cell:
                            # eat from both
                            a_next_element = cell_a_element
                            b_next_element = cell_b_element
                            move_score = DEFAULT_GOOD_SCORE

                        if next_cell == delete_cell:
                            # eat from A only
                            a_next_element = cell_a_element
                        if next_cell == insert_cell:
                            # eat from B only
                            b_next_element = cell_b_element

                        if self.alignment_scores is not None:
                            move_score = DEFAULT_GOOD_SCORE
                            # make sure it's an allowed move
                            try:
                                move_score = self.alignment_scores[a_next_element][b_next_element]
                            except KeyError:
                                # can't make this move
                                continue

                        # add the next cell to the current path
                        #  and update the score
                        cells_so_far = path.cells
                        score_so_far = path.score
                        new_path = ViterbiPath(cells_so_far+[next_cell],
                                               DEFAULT_SCORE_COMBINATION(score_so_far,
                                                                         move_score))

                        # then add the new path to the next cell
                        next_cell.paths.append(new_path)

    def get_all_paths(self):
        last_cell = self.grid[-1][-1]
        return last_cell.get_all_paths()

    def get_best_paths(self):
        last_cell = self.grid[-1][-1]
        return last_cell.get_best_paths()

    def print_grid(self, what='coordinates'):
        """This could use some formatting work"""
        grid = []

        for row in self.grid:
            grid_row = []
            for cell in row:
                if what == 'npaths':
                    val = len(cell.get_all_paths())
                elif what == 'names':
                    val = cell.get_name()
                else:
                    val = (cell.row_idx, cell.col_idx)
                grid_row.append(val)

            grid.append(grid_row)

        for row in grid[::-1]:
            print row
