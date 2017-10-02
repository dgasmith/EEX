"""
Contains the DataLayer class (name in progress) which takes and reads various peices of data
"""

import os
import pandas as pd
import numpy as np
import collections

import eex
from . import filelayer
from . import metadata
from . import units

APC_DICT = metadata.atom_property_to_column


class DataLayer(object):
    def __init__(self, name, store_location=None, save_data=False, backend="HDF5"):
        """
        Initializes the DataLayer class

        Parameters
        ----------
        name : str
            The name of the energy expression stored
        store_location : {None, str}, optional
            The location to store the temporary data during the translation. Defaults to the current working directory.
        save_data : {False, True}, optional
            Decides whether to delete the store data upon destruction of the DataLayer object.
        backend : {"HDF5", "memory"}, optional
            Storage backend for the energy expression.
        """

        # Set the state
        self.name = name

        # Build the store
        self.store_location = store_location
        if self.store_location is None:
            self.store_location = os.getcwd()

        if backend.upper() == "HDF5":
            self.store = filelayer.HDFStore(self.name, self.store_location, save_data)
        elif backend.upper() == "MEMORY":
            self.store = filelayer.MemoryStore(self.name, self.store_location, save_data)
        else:
            raise KeyError("DataLayer: Backend of type '%s' not recognized." % backend)

        # Setup empty parameters dictionary
        self._functional_forms = {2: {}, 3: {}, 4: {}, 5: {}, 6: {}, 7: {}}
        self._terms = {2: {}, 3: {}, 4: {}, 5: {}, 6: {}, 7: {}}
        self._atom_metadata = {}

### Generic helper close/save/list/etc functions

    def call_by_string(self, *args, **kwargs):
        """
        Adds the ability to call DL function by their string name.
        """

        if args[0] == "NYI":
            return False

        try:
            function = getattr(self, args[0])
        except:
            raise KeyError("DataLayer:call_by_string: does not have method %s." % args[0])

        return function(*args[1:], **kwargs)

    def close(self):
        """
        Closes the DL object
        """
        self.store.close()

    def list_tables(self):
        """
        Lists tables loaded into the store.
        """
        return [x for x in self.store.list_tables() if "other" not in x]

    def list_other_tables(self):
        """
        Lists "other" tables loaded into the store.
        """
        return [x.replace("other_", "") for x in self.store.list_tables() if "other" in x]

### Atom functions

    def _check_atoms_dict(self, property_name):
        if property_name in list(self._atom_metadata):
            return False

        field_data = metadata.atom_metadata[property_name]
        self._atom_metadata[property_name] = {"counter": -1, "uvals": {}, "inv_uvals": {}}

        return True

    def _find_unqiue_atom_values(self, df, property_name):
        """
        Hashes the input parameters to build in internal index of unique values.
        """

        field_data = metadata.atom_metadata[property_name]
        param_dict = self._atom_metadata[property_name]

        cols = field_data["required_columns"]

        if field_data["dtype"] == float:
            df = df[cols].round(field_data["tol"])

        ret_df = pd.DataFrame(index=df.index)
        ret_df[property_name] = 0

        # For each unique value
        for gb_idx, udf in df.groupby(cols):

            # Update dictionary if necessary
            if gb_idx not in list(param_dict["uvals"]):
                param_dict["counter"] += 1

                # Bidirectional dictionary
                param_dict["uvals"][gb_idx] = param_dict["counter"]
                param_dict["inv_uvals"][param_dict["counter"]] = gb_idx

            # Grab the unique and set
            uidx = param_dict["uvals"][gb_idx]
            ret_df.loc[udf.index, property_name] = uidx

        return ret_df

    def _build_atom_values(self, df, property_name):
        """
        Expands the unique parameters using the built in property_name dictionary.
        """
        field_data = metadata.atom_metadata[property_name]
        param_dict = self._atom_metadata[property_name]

        cols = field_data["required_columns"]

        ret_df = pd.DataFrame(index=df.index)
        ret_df[property_name] = 0.0

        for gb_idx, udf in df.groupby(cols):
            ret_df.loc[udf.index, property_name] = param_dict["inv_uvals"][gb_idx]

        return ret_df

    def _store_atom_table(self, table_name, df, property_name, by_value, utype):
        """
        Internal way to store atom tables
        """

        self._check_atoms_dict(property_name)
        field_data = metadata.atom_metadata[property_name]

        # Figure out unit scaling factors
        if by_value and (field_data["units"] is not None) and (utype is not None):
            scale_factor = units.conversion_factor(utype, field_data["utype"])
            df = df[field_data["required_columns"]] * scale_factor

        if by_value and not (metadata.atom_metadata[property_name]["unique"]):
            tmp_df = self._find_unqiue_atom_values(df, property_name)
        else:
            tmp_df = df[APC_DICT[property_name]]

        return self.store.add_table(table_name, tmp_df)

    def _get_atom_table(self, table_name, property_name, by_value, utype):

        tmp = self.store.read_table(table_name)
        if by_value and not (metadata.atom_metadata[property_name]["unique"]):
            tmp = self._build_atom_values(tmp, property_name)

        # Figure out unit scaling factors
        field_data = metadata.atom_metadata[property_name]
        if by_value and (field_data["units"] is not None) and (utype is not None):
            scale_factor = units.conversion_factor(field_data["utype"], utype)
            tmp[field_data["required_columns"]] *= scale_factor

        return tmp

    def add_atoms(self, atom_df, property_name=None, by_value=False, utype=None):
        """
        Adds atom information to the DataLayer object.

        Parameters
        ----------
        atom_df : {DataFrame, list, tuple}
            The atom data to add to the object.
        property_name : {list, str}, optional
            The atom property that is added, only necessary if a list is passed in.
        by_value : bool
            If data is passed by_value the DL automatically hashes the parameters to unique components.
        utype : {dict, pint.Unit}
            The unit type of the atom_df.

        Returns
        -------
        return : bool
            If the add was successful or not.

        Example
        -------
        dl = DataLayer("test")

        # Add the XYZ information for five random atoms
        tmp_df = pd.DataFrame(np.random.rand(5, 3), columns=["X", "Y", "Z"])
        tmp_df["atom_index"] = np.arange(5)
        dl.add_atom(tmp_df)
        """

        # Our index name
        index = "atom_index"

        # Validate DataFrame
        if not isinstance(atom_df, pd.DataFrame):
            raise KeyError("DataLayer:add_atoms: Data type '%s' not understood." % type(atom_df))

        if index in atom_df.columns:
            atom_df = atom_df.set_index(index, drop=True)

        if atom_df.index.name != index:
            raise KeyError("DataLayer:add_atoms: DF index must be the `atom_index` not '%s'." % atom_df.index.name)

        if utype is None:
            utype = {}
        elif isinstance(utype, dict):
            utype = {k.lower(): v for k, v in utype.items()}
        else:
            raise TypeError("utype type not understood")

        # Try to add all possible properties
        set_cols = set(atom_df.columns)
        found_one = False
        for k, v in APC_DICT.items():
            # Check if v is in the set_cols (set logic)
            if set(v) <= set_cols:
                uval = None
                if k in utype:
                    uval = utype[k]
                self._store_atom_table(k, atom_df, k, by_value, uval)
                found_one = True
        if not found_one:
            raise Exception("DataLayer:add_atom: No data was added as no key was matched from input columns:\n%s" %
                            (" " * 11 + str(atom_df.columns)))

        return True

    def get_atoms(self, properties, by_value=False, utype=None):
        """
        Obtains atom information to the DataLayer object.

        Parameters
        ----------
        properties : {list, str}
            The properties to obtain for the atom data.
        by_value : bool
            If true returns the property by value, otherwise returns by index.

        Returns
        -------
        return : pd.DataFrame
            Returns a DataFrame containing the atom property information
            If the add was successful or not.

        """

        valid_properties = list(metadata.atom_property_to_column)

        # Our index name
        if not isinstance(properties, (tuple, list)):
            properties = [properties]

        properties = [x.lower() for x in properties]

        if not set(properties) <= set(list(valid_properties)):
            invalid_props = set(properties) - set(list(valid_properties))
            raise KeyError("DataLayer:add_atoms: Property name(s) '%s' not recognized." % str(list(invalid_props)))

        if utype is None:
            utype = {}
        elif isinstance(utype, dict):
            utype = {k.lower(): v for k, v in utype.items()}
        else:
            raise TypeError("utype type not understood")

        df_data = []
        for prop in properties:
            uval = None
            if prop in utype:
                uval = utype[prop]
            tmp = self._get_atom_table(prop, prop, by_value, uval)
            df_data.append(tmp)

        return pd.concat(df_data, axis=1)

### Term functions

    def register_functional_forms(self, order, name, form=None, utype=None):
        """
        Registers a single functional forms with the DL object.

        Parameters
        ----------
        order : int
            The order of the functional form (2, 3, 4, ...)
        name : str
            The name of the functional form you are adding
        form : dict
            The metadata for the incoming form. Follows the term order descriptions.
        utype : {dict, pint.Unit}
            The unit type of the functional form.

        Returns
        -------
        pass : bool
            If the operation was sucessfull or not.


        Examples
        --------

        # Register form by passing in explicit data
        form_metadata = {
            "form": "K*(r-R0) ** 2",
            "parameters": ["K", "R0"],
            "units": {
                "K": "kcal * mol ** 2",
                "R0": "picometers"
            },
            "description": "This is a harmonic bond"
        }

        dl.register_functional_form(2, "custom_harmonic", form=form_metadata)

        # Register form by using EEX build-in forms and setting units
        dl.register_functional_form(2, "harmonic", units={"K": "(kcal / mol) / angstrom ** 2", "R0": "picometers"})
        """

        user_order = order
        order = metadata.sanitize_term_order_name(order)

        if order not in self._functional_forms:
            raise KeyError("DataLayer:register_functional_forms: Did not understand order key '%s'." % str(user_order))

        # We are using an internal form
        if (form is None) and (utype is None):
            raise KeyError(
                "DataLayer:register_functional_forms: Must either pass in form (external form) or units (internal form)."
            )

        elif form is None:
            if utype is None:
                raise KeyError("DataLayer:register_functional_forms: Must pass in units if using a EEX built-in form.")

            try:
                form = metadata.get_term_metadata(order, "forms", name)
            except KeyError:
                raise KeyError(
                    "DataLayer:register_functional_forms: Could not find built in form of order `%s` and name `%s" %
                    (str(user_order), str(name)))

            form["units"] = utype

        # We are using an external form
        else:
            if name in self._functional_forms[order]:
                raise KeyError(
                    "DataLayer:register_functional_forms: Key '%s' has already been registered." % str(name))
            # Pass validator later

        assert metadata.validate_functional_form_dict(name, form)

        # Make sure the data is valid and add
        self._functional_forms[order][name] = form

    def add_parameters(self, order, term_name, term_parameters, uid=None, utype=None):
        """
        Adds the parameters of a registered functional form to the Datalayer object

        Parameters
        ----------
        order : int
            The order of the functional form (2, 3, 4, ...)
        term_name : str
            The name of the functional form you are adding.
        term_parameters : {list, tuple, dict}
            The parameters to the functional form you are adding. If a list or tuple the order matches the order supplied
            in the functional form. Otherwise the dictionary matches functional form parameter names.
        uid : int, optional
            The uid to assign to this parameterized term.
        utype : list of Pint units, options
            Custom units for this particular addition, otherwise uses the default units in the registered functional form.

        Examples
        --------

        assert 0 == dl.add_parameters(2, "harmonic", [4.0, 5.0])
        assert 0 == dl.add_parameters(2, "harmonic", [4.0, 5.0])
        assert 1 == dl.add_parameters(2, "harmonic", [4.0, 6.0])

        """

        user_order = order
        order = metadata.sanitize_term_order_name(order)

        # Validate term add
        if order not in list(self._functional_forms):
            raise KeyError("DataLayer:register_functional_forms: Did not understand order key '%s'." % str(user_order))

        if term_name not in list(self._functional_forms[order]):
            raise KeyError(
                "DataLayer:register_functional_forms: Term name '%s' has not been registered." % str(term_name))

        if utype:
            raise TypeError("DataLayer:register_functional_forms: Units are not yet supported, contact @dgasmith.")

        # Obtain the parameters
        mdata = self._functional_forms[order][term_name]
        params = metadata.validate_term_dict(term_name, mdata, term_parameters)

        # First we check if we already have it
        found_key = None
        for k, v in self._terms[order].items():
            if (v[0] == term_name) and np.allclose(v[1:], params):
                found_key = k
                break

        # Figure out what actually to do
        if uid is None:

            if found_key is not None:
                return found_key

            # We have a new parameter! Find the lowest number that we can add it at.
            if not len(self._terms[order]):
                new_key = 0
            else:
                possible_values = set(range(len(self._terms[order]) + 1))
                new_key = min(possible_values - set(self._terms[order]))

            params.insert(0, term_name)
            self._terms[order][new_key] = params

            return new_key

        else:

            if not isinstance(uid, int):
                raise TypeError(
                    "DataLayer:register_functional_forms: uid keyword must be of type int, found type '%s'." %
                    type(uid))

            # If we exist this could get dangerous
            if uid in self._terms[order]:
                old_param = self._terms[order][uid]
                match = (old_param[0] == term_name) and np.allclose(old_param[1:], params)
                if not match:
                    raise KeyError(
                        "DataLayer:register_functional_forms: uid already exists, but does not much current parameters."
                    )
                else:
                    return uid

            else:
                params.insert(0, term_name)
                self._terms[order][uid] = params

                return uid

    def add_terms(self, order, df):

        order = metadata.sanitize_term_order_name(order)
        if order not in list(self._functional_forms):
            raise KeyError("DataLayer:add_terms: Did not understand order key '%s'." % str(order))

        req_cols = metadata.get_term_metadata(order, "index_columns")

        not_found = set(req_cols) - set(df.columns)
        if not_found:
            raise KeyError("DataLayer:add_terms: Missing required columns '%s' for order %d" % (str(not_found), order))

        if "term_index" in df.columns:
            df = df[req_cols + ["term_index"]]
        else:
            raise Exception("NYI: Add terms by *not* term_index")
        self.store.add_table("term" + str(order), df)

    def read_terms(self, order):
        order = metadata.sanitize_term_order_name(order)
        if order not in list(self._functional_forms):
            raise KeyError("DataLayer:add_terms: Did not understand order key '%s'." % str(order))

        return self.store.read_table("term" + str(order))

    def add_bonds(self, bonds):
        """
        Adds bond using a index notation.

        Parameters
        ----------
        bonds : pd.DataFrame
            Adds a DataFrame containing the bond information by index
            Required columns: ["bond_index", "atom1_index", "atom2_index", "bond_type"]

        Returns
        -------
        return : bool
            Returns a boolean value if the operations was successful or not
        """

        self.add_terms("bonds", bonds)

        return True

    def get_bonds(self):

        return self.read_terms("bonds")

    def add_angles(self, angles):

        self.add_terms("angles", angles)

    def get_angles(self):

        return self.read_terms("angles")

    def add_dihedrals(self, dihedrals):

        self.add_terms("dihedrals", dihedrals)

    def get_dihedrals(self):

        return self.read_terms("dihedrals")

### Other quantities

    def add_other(self, key, df):
        """
        Adds arbitrary data to the DataLayer object. This data is effectively private and will not be used by any part
        of EEX.

        Parameters
        ----------
        key : str
            The key to store the data under.
        df : pd.DataFrame
            Adds a DataFrame containing data

        Returns
        -------
        return : bool
            Returns a boolean value if the operations was successful or not
        """

        key = "other_" + key
        self.store.add_table(key, df)

        return True

    def get_other(self, key):
        """
        Obtains other information from the DataLayer object.
        """

        if not isinstance(key, (tuple, list)):
            key = [key]

        tmp_data = []
        for k in key:
            k = "other_" + k
            tmp_data.append(self.store.read_table(k))

        return pd.concat(tmp_data, axis=1)
