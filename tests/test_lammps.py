"""
Tests for LAMMPS IO
"""
import eex
import numpy as np
import pytest
import pandas as pd
import eex_find_files


@pytest.fixture(scope="module", params=["HDF5", "Memory"])
def spce_dl(request):
    fname = eex_find_files.get_example_filename("lammps", "SPCE", "data.spce")
    dl = eex.datalayer.DataLayer(
        "test_lammps_read", )
    data = eex.translators.lammps.read_lammps_file(dl, fname, blocksize=55)
    yield (data, dl)
    dl.close()


def test_lammps_read_data(spce_dl):
    data, dl = spce_dl

    # Check on the data dictionary
    assert data["sizes"]["atoms"] == 600
    assert data["sizes"]["bonds"] == 400
    assert data["sizes"]["angles"] == 200
    assert data["sizes"]["angle types"] == 1

    box_size = dl.get_box_size()
    assert box_size["x"][0] == pytest.approx(-12.362, 1.e-6)
    assert box_size["x"][1] == pytest.approx(12.362, 1.e-6)


def test_lammps_read_atoms(spce_dl):
    data, dl = spce_dl

    # Check Atoms
    atoms = dl.get_atoms(["atom_type", "charge", "mass"])
    assert atoms.shape[0] == 600
    assert np.allclose(np.unique(atoms["atom_type"]), [1, 2])
    assert np.allclose(np.unique(atoms["charge"]), [0, 1])
    assert np.allclose(np.unique(atoms["mass"]), [1, 2])


def test_lammps_read_atoms_value(spce_dl):
    data, dl = spce_dl

    # Check Atoms
    atoms = dl.get_atoms(["atom_type", "charge", "mass"], by_value=True)
    assert atoms.shape[0] == 600
    assert np.allclose(np.unique(atoms["atom_type"]), [1, 2])
    assert np.allclose(np.unique(atoms["charge"]), [-0.8476, 0.4238])
    assert np.allclose(np.unique(atoms["mass"]), [1.008, 16.000])


def test_lammps_read_bonds(spce_dl):
    data, dl = spce_dl

    # Check Bonds
    bonds = dl.get_bonds()
    assert bonds.shape[0] == 400
    assert np.allclose(np.unique(bonds["term_index"]), [1])


def test_lammps_read_angles(spce_dl):
    data, dl = spce_dl

    # Check Angles
    angles = dl.get_angles()
    assert angles.shape[0] == 200
    assert np.allclose(np.unique(angles["term_index"]), [1])
