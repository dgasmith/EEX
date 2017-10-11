"""
LAMMPS EEX I/O
"""

import pandas as pd
import math
import numpy as np
import eex

from . import lammps_metadata as lmd

import logging
logger = logging.getLogger(__name__)


def write_lammps_file(dl, data, filename, blocksize=110):

    term_table = lmd.build_term_table("real")

    with open(filename, 'w') as data_file:

        data_file.write("LAMMPS data file generated by MolSSI EEX\n\n")

        sizes = {}
        sizes["atoms"] = dl.get_atom_count()
        sizes["bonds"] = dl.get_term_count(2, "total")
        sizes["angles"] = dl.get_term_count(3, "total")
        sizes["dihedrals"] = dl.get_term_count(4, "total") # Not qutie right once we do impropers
        sizes["impropers"] = 0
        sizes["atom types"] = len(dl.get_atom_uids("mass"))

        # All the UID's minus the "total" columns
        sizes["bond types"] = len(dl.get_term_count(2)) - 1
        sizes["angle types"] = len(dl.get_term_count(2)) - 1
        sizes["dihedral types"] = len(dl.get_term_count(2)) - 1
        sizes["improper types"] = 0

        # Write header information
        for k in lmd.size_keys:
            data_file.write(" %d %s\n" % (sizes[k], k))
            # data_file.write(' '.join([str(data["sizes"][k]), k, '\n']))

        # Write box information
        box_size = dl.get_box_size()
        for coord in ["x", "y", "z"]:
            data_file.write("% 8.6f% 8.6f %slo %shi\n" % (box_size[coord][0], box_size[coord][1], coord, coord))
        data_file.write('\n')

        # Loop over Pair Coeffs
        # NYI

        # Loop over all of the parameter data
        param_fmt = "%10.8f"
        for param_order, param_type in zip([2, 3, 4], ["bonds", "angles", "dihedrals"]):
            param_uids = dl.list_parameter_uids(param_type)

            if len(param_uids) == 0: continue

            data_file.write(("%s Coeffs\n\n" % param_type).title())
            for uid in param_uids:
                param_coeffs = dl.get_parameter(param_type, uid)
                term_data = term_table[param_order][param_coeffs[0]]
                param_coeffs = dl.get_parameter(param_type, uid, utype=term_data["utype"])

                # Order the data like lammps wants it
                parameters = [param_coeffs[1][k] for k in term_data["parameters"]]

                data_file.write("%2d " % uid)
                data_file.write(" ".join(param_fmt % f for f in parameters))
                data_file.write("\n")
                # value_list = list(bond_coeffs[1].values())
                # value_string = ' '.join(str(x) for x in value_list)
                # data_file.write(' '.join([str(uid), value_string, '\n']))
            data_file.write("\n")

        # Write out mass data
        data_file.write(" Masses\n\n")
        for idx, mass in dl.get_atom_uids("mass", properties=True).items():
            data_file.write("%2d %10.8f\n" % (idx, mass))
        data_file.write('\n')

        # Write out atom data
        data_file.write(" Atoms\n\n")

        atoms = dl.get_atoms(["molecule_index", "atom_type", "charge", "xyz"], by_value=True)
        atoms.index = pd.RangeIndex(start=1, stop=atoms.shape[0] + 1)

        # Build a simple formatter
        def float_fmt(n):
            return "%10.8f" % n
        atoms.to_string(data_file, header=None, float_format=float_fmt)
        data_file.write('\n\n')

        # # Switching over to a NumPy based approach for speed
        # data_file.close()

        # Write out all of the term data
        for param_order, param_type in zip([2, 3, 4], ["bonds", "angles", "dihedrals"]):
            if sizes[param_type] == 0: continue

            data_file.write((" %s\n\n" % param_type).title())

            # Grab term and reorder
            cols = ["term_index"] + ["atom%s" % d for d in range(1, param_order + 1)]
            term = dl.get_terms(param_type)[cols]
            term.index = pd.RangeIndex(start=1, stop=term.shape[0] + 1)
            # print(term)
            term.to_csv(data_file, header=None, sep=" ")
            data_file.write('\n')

