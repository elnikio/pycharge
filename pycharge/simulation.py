#!/usr/bin/env python
"""Module contains the `Simulation` class and helper functions for save files.

The `Simulation` class is used to calculate the electromagnetic fields and
potentials generated by moving point charges, which are defined by the `Charge`
base class. The values are determined numerically at each grid point by
evaluating the Liénard–Wiechert potentials and corresponding electromagnetic
field equations at the retarded time.

The `Simulation` class also runs simulations using the `Dipole` class by
dynamically calculating the dipole moment at each time step using the
`run` method. Treating the dipole as a Lorentz oscillator, the differential
equation of motion is solved at each time step using the RK4 method. The
driving electric field acting on the dipole is the component of the external
electric field in the direction of polarization generated by the other point
charges in the simulation. After the simulation is run, the `Simulation` object
can calculate the electromagnetic fields and potentials generated by the
`Dipole` objects within the timespan of the simulation.

All units are in SI.
"""
from __future__ import annotations

from typing import Any, Callable, Optional, Sequence, Tuple, Union

import dill as pickle
import numpy as np
from numpy import ndarray
from scipy import constants, optimize
from tqdm import tqdm

from .charges import Charge
from .dipole import Dipole

# Constants
eps = constants.epsilon_0
mu_0 = constants.mu_0
pi = constants.pi
e = constants.e
c = constants.c


class Simulation():
    """Primary class for electromagnetism calculations using `PyCharge`.

    The `Simulation` class calculates the electromagnetic fields and potentials
    generated by point charges that are subclasses of the `Charge` base class
    and have predefined trajectories.

    The `Simulation` class also run simulations with `Dipole` objects over a
    range of time steps to dynamically determine their dipole moment. The
    dipoles behave as Lorentz oscillators and their dipole moment and related
    trajectories are calculated at each time step.

    Args:
        sources (Union[Sequence, Union[Charge, Dipole]]): Either a single or
            list of `Dipole` and `Charge` object(s) in the simulation.
        E_field (Callable[[float, float, float, float], ndarray]): Function
            returning the external electric field components. Parameters are
            time, x, y, and z. Default is `None`.
        B_field (Callable[[float, float, float, float], ndarray]): Function
            returning the external magnetic field components. Parameters are
            time, x, y, and z. Default is `None`.
        h (float): Tolerance for Newton's method. Default is `1e-22`.
    """

    def __init__(
        self,
        sources: Union[Sequence, Union[Charge, Dipole]],
        E_field: Callable[[float, float, float, float], ndarray] = None,
        B_field: Callable[[float, float, float, float], ndarray] = None,
        h: float = 1e-22
    ) -> None:
        self.E_field = E_field  # External E field
        self.B_field = B_field  # External B field
        self.h = h
        self.all_charges = []  # List of all `Charge` objects
        self.dipoles = []  # List of `Dipole` objects
        if not isinstance(sources, Sequence):
            sources = [sources]  # Convert to a list
        for source in sources:
            if isinstance(source, Dipole):
                self.dipoles.append(source)
                self.all_charges.append(source.charge_pair[0])
                self.all_charges.append(source.charge_pair[1])
            else:
                self.all_charges.append(source)
        # Initialize attributes below in `run` method
        self.timesteps = None
        self.dt = None
        self.save_E = None

    def __eq__(self, other: Any) -> bool:
        return (isinstance(other, self.__class__) and self.dt == other.dt
                and self.all_charges == other.all_charges
                and self.timesteps == other.timesteps)

    def _save(self, file: str) -> None:
        """Save the `Simulation` object to a file."""
        with open(file, "ab") as f:
            pickle.dump(self, f)

    def _load(self, file: str) -> bool:
        """Load the `Simulation` object from a file."""
        try:
            with open(file, "rb") as f:
                loaded_simulation = pickle.load(f)
                while self != loaded_simulation:
                    loaded_simulation = pickle.load(f)
                # pylint: disable=E1101
                for dipole, loaded_dipole in zip(self.dipoles,
                                                 loaded_simulation.dipoles):
                    dipole.__dict__ = loaded_dipole.__dict__
                return True
        except (FileNotFoundError, EOFError):
            return False

    def calculate_E(
        self,
        t: float,
        x: ndarray,
        y: ndarray,
        z: ndarray,
        pcharge_field: str = 'Total',
        exclude_charges: Sequence = None
    ) -> ndarray:
        """Calculate the electric field (E) generated by the point charge(s).

        Meshgrid must use matrix indexing ('ij').

        Args:
            t: Time of simulation.
            x: Meshgrid of x values.
            y: Meshgrid of y values.
            z: Meshgrid of z values.
            pcharge_field: Determines which field is returned: `Velocity`,
                `Acceleration`, or `Total`. Defaults to `Total`.
            exclude_charges: List of charges to exclude in calculation of the
                electric field. Defaults to None.

        Returns:
            List of E_x, E_y, and E_z.
        """
        t_array = np.ones((x.shape))
        t_array[:, :, :] = t
        Ex = np.zeros((x.shape))
        Ey = np.zeros((x.shape))
        Ez = np.zeros((x.shape))
        for charge in self.all_charges:
            if exclude_charges is not None and charge in exclude_charges:
                continue
            initial_guess = -1e-12*np.ones((x.shape))
            tr = optimize.newton(charge.solve_time, initial_guess,
                                 args=(t_array, x, y, z), tol=self.h)
            E_field = self._calculate_individual_E(
                charge, tr, x, y, z, pcharge_field)
            Ex += E_field[0]
            Ey += E_field[1]
            Ez += E_field[2]
        if self.E_field is not None:  # Add external E field
            Ex += self.E_field(t, x, y, z)[0]
            Ey += self.E_field(t, x, y, z)[1]
            Ez += self.E_field(t, x, y, z)[2]
        return np.array((Ex, Ey, Ez))

    def calculate_B(
        self,
        t: float,
        x: ndarray,
        y: ndarray,
        z: ndarray,
        pcharge_field: str = 'Total',
        exclude_charges: Sequence = None
    ) -> ndarray:
        """Calculate the magnetic field (B) generated by the point charge(s).

        Args:
            t: Time of simulation.
            x: Meshgrid of x values.
            y: Meshgrid of y values.
            z: Meshgrid of z values.
            pcharge_field: Determines which field is returned:
                `Velocity`, `Acceleration`, or `Total`. Defaults to `Total`.
            exclude_charges: List of charges to exclude in calculation of the
                magnetic field. Defaults to None.

        Returns:
            List of Bx, By, and Bz.
        """
        t_array = np.ones((x.shape))
        t_array[:, :, :] = t
        Bx = np.zeros((x.shape))
        By = np.zeros((x.shape))
        Bz = np.zeros((x.shape))
        for charge in self.all_charges:
            if exclude_charges is not None and charge in exclude_charges:
                continue
            initial_guess = -1e-12*np.ones((x.shape))
            tr = optimize.newton(charge.solve_time, initial_guess,
                                 args=(t_array, x, y, z), tol=self.h)
            E_x, E_y, E_z = self._calculate_individual_E(
                charge, tr, x, y, z, pcharge_field)
            rx = x - charge.xpos(tr)
            ry = y - charge.ypos(tr)
            rz = z - charge.zpos(tr)
            r_mag = (rx**2 + ry**2 + rz**2)**0.5
            Bx += 1/(c*r_mag)*(ry*E_z-rz*E_y)
            By += 1/(c*r_mag)*(rz*E_x-rx*E_z)
            Bz += 1/(c*r_mag)*(rx*E_y-ry*E_x)
        if self.B_field is not None:  # Add external B field
            Bx += self.B_field(t, x, y, z)[0]
            By += self.B_field(t, x, y, z)[1]
            Bz += self.B_field(t, x, y, z)[2]
        return np.array((Bx, By, Bz))

    def calculate_V(
        self,
        t: float,
        x: ndarray,
        y: ndarray,
        z: ndarray,
        exclude_charges: Sequence = None
    ) -> ndarray:
        """Calculate the scalar potential (V) generated by the point charge(s).

        Args:
            t: Time of simulation.
            x: Meshgrid of x values.
            y: Meshgrid of y values.
            z: Meshgrid of z values.
            exclude_charges: List of charges to exclude in calculation of the
                potentials. Defaults to None.

        Returns:
            Scalar potential V.
        """
        t_array = np.ones((x.shape))
        t_array[:, :, :] = t
        V = np.zeros((x.shape))
        for charge in self.all_charges:
            if exclude_charges is not None and charge in exclude_charges:
                continue
            initial_guess = -1e-12*np.ones((x.shape))
            tr = optimize.newton(charge.solve_time, initial_guess,
                                 args=(t_array, x, y, z), tol=self.h)
            rx = x - charge.xpos(tr)
            ry = y - charge.ypos(tr)
            rz = z - charge.zpos(tr)
            r_mag = (rx**2 + ry**2 + rz**2)**0.5
            vx = charge.xvel(tr)  # retarded velocity - Griffiths Eq. 10.54
            vy = charge.yvel(tr)
            vz = charge.zvel(tr)
            r_dot_v = rx*vx + ry*vy + rz*vz
            # Griffiths Eq. 10.53
            V += charge.q*c/(4*pi*eps*(r_mag*c-r_dot_v))
        return V

    def calculate_A(
        self,
        t: float,
        x: ndarray,
        y: ndarray,
        z: ndarray,
        exclude_charges: Sequence = None
    ) -> Tuple[ndarray, ndarray, ndarray]:
        """Calculate the vector potential (A) generated by the point charge(s).

        Args:
            t: Time of simulation.
            x: Meshgrid of x values.
            y: Meshgrid of y values.
            z: Meshgrid of z values.
            exclude_charges: List of charges to exclude in calculation of the
                potentials. Defaults to None.

        Returns:
            List of Ax, Ay, and Az.
        """
        t_array = np.ones((x.shape))
        t_array[:, :, :] = t
        Ax = np.zeros((x.shape))
        Ay = np.zeros((x.shape))
        Az = np.zeros((x.shape))
        for charge in self.all_charges:
            if exclude_charges is not None and charge in exclude_charges:
                continue
            initial_guess = -1e-12*np.ones((x.shape))
            tr = optimize.newton(charge.solve_time, initial_guess,
                                 args=(t_array, x, y, z), tol=self.h)
            rx = x - charge.xpos(tr)
            ry = y - charge.ypos(tr)
            rz = z - charge.zpos(tr)
            r_mag = (rx**2 + ry**2 + rz**2)**0.5
            vx = charge.xvel(tr)  # retarded velocity - Griffiths Eq. 10.54
            vy = charge.yvel(tr)
            vz = charge.zvel(tr)
            r_dot_v = rx*vx + ry*vy + rz*vz
            # Griffiths Eq. 10.53
            individual_V = charge.q*c/(4*pi*eps*(r_mag*c-r_dot_v))
            # Griffiths Eq. 10.53
            Ax += vx/c**2*individual_V
            Ay += vy/c**2*individual_V
            Az += vz/c**2*individual_V
        return (Ax, Ay, Az)

    def _calculate_individual_E(  # pylint: disable=R1710, R0201
        self,
        charge: Charge,
        tr: ndarray,
        x: ndarray,
        y: ndarray,
        z: ndarray,
        pcharge_field: str
    ) -> Tuple[ndarray, ndarray, ndarray]:
        """Calculate the electric field generated by an individual charge."""
        rx = x - charge.xpos(tr)  # Griffiths Eq. 10.54
        ry = y - charge.ypos(tr)
        rz = z - charge.zpos(tr)
        r_mag = (rx**2 + ry**2 + rz**2)**0.5
        vx = charge.xvel(tr)
        vy = charge.yvel(tr)
        vz = charge.zvel(tr)
        ax = charge.xacc(tr)
        ay = charge.yacc(tr)
        az = charge.zacc(tr)
        ux = c*rx/r_mag - vx  # Griffiths Eq. 10.71
        uy = c*ry/r_mag - vy
        uz = c*rz/r_mag - vz
        r_dot_u = rx*ux + ry*uy + rz*uz
        r_dot_a = rx*ax + ry*ay + rz*az
        vel_mag = (vx**2 + vy**2 + vz**2)**0.5
        # Griffiths Eq. 10.72
        const = charge.q/(4*pi*eps) * r_mag/(r_dot_u)**3
        xvel_field = const*(c**2-vel_mag**2)*ux
        yvel_field = const*(c**2-vel_mag**2)*uy
        zvel_field = const*(c**2-vel_mag**2)*uz
        # Using triple product rule to simplify Eq. 10.72
        xacc_field = const*(r_dot_a*ux - r_dot_u*ax)
        yacc_field = const*(r_dot_a*uy - r_dot_u*ay)
        zacc_field = const*(r_dot_a*uz - r_dot_u*az)
        if pcharge_field == 'Velocity':
            return (xvel_field, yvel_field, zvel_field)
        if pcharge_field == 'Acceleration':
            return (xacc_field, yacc_field, zacc_field)
        if pcharge_field == 'Total':
            return (xvel_field+xacc_field, yvel_field+yacc_field,
                    zvel_field+zacc_field)

    def run(
        self,
        timesteps: int,
        dt: float,
        file: Optional[str] = None,
        save_E: bool = False,
        max_vel: float = c/100,
        progressbar: bool = True
    ) -> None:
        """Run simulation with `Dipole` and `Charge` object(s).

        Simulation calculates the dipole moment and corresponding derivatives
        at each time step by solving the equation of motion using the RK4
        method. The position, velocity, and acceleration values are then
        updated in the `Dipole` object.

        Args:
            timesteps (int): Number of time steps run during the simulation.
            dt (float): Time step.
            file: File name to load/save `Simulation`. Defaults to `None`.
            save_E (bool): If True, the driving field acting on each dipole is
                saved at each time step. However, this comes at a cost to speed
                and memory. Defaults to `True`.
            max_vel: The maximum possible velocity achieved by the two point
                charges in `Dipole` object. Defaults to `c/100`.
            progressbar: Prints the progressbar if `True`. Defaults to `True`.

        Raises:
            ValueError: Raised if the point charge's velocity in the `Dipole`
                object becomes larger than `max_vel`.
        """
        self._init_simulation(timesteps, dt, save_E)
        if file is not None and self._load(file):
            return
        for tstep in tqdm(range(self.timesteps-1), total=self.timesteps,
                          initial=1, mininterval=0.5, disable=not progressbar):
            for dipole in self.dipoles:
                moment_disp, moment_vel = self._rk4(tstep, dipole)
                self._update_dipole(tstep, dipole, moment_disp, moment_vel,
                                    max_vel)
        if file is not None:
            self._save(file)

    def run_mpi(
        self,
        timesteps: int,
        dt: float,
        file: Optional[str] = None,
        save_E: bool = False,
        max_vel: float = c/100,
        progressbar: bool = True
    ) -> None:
        """Run simulation with `Dipole` and `Charge` object(s) using MPI.

        Method exploits MPI to speed up the simulation. In the ideal case, the
        number of MPI processors and the number of `Dipole` objects are equal.
        Most efficient simulation occurs when `save_E` is `False`.

        Simulation calculates the dipole moment and corresponding derivatives
        at each time step by solving the equation of motion using the RK4
        method. The position, velocity, and acceleration values are then
        updated in the `Dipole` object.

        Args:
            timesteps (int): Number of time steps run during the simulation.
            dt (float): Time step.
            file: File name to load/save `Simulation`. Defaults to `None`.
            save_E (bool): If True, the driving field acting on each dipole is
                saved at each time step. However, this comes at a cost to speed
                and memory. Defaults to `True`.
            max_vel: The maximum possible velocity achieved by the two point
                charges in `Dipole` object. Defaults to `c/100`.
            progressbar: Prints the progressbar if `True`. Defaults to `True`.

        Raises:
            NotImplementedError: Raised if `mpi4py` package is not installed.
            ValueError: Raised if the point charge's velocity in the `Dipole`
                object becomes larger than `max_vel`.

        Example:
            An MPI program can be run from a script with the command mpiexec:
                >> $ mpiexec -n 4 python script.py
            Here, 4 separate processes will be initiated to run script.py.
        """
        try:
            from mpi4py import MPI  # pylint: disable=import-outside-toplevel
        except ImportError:
            NotImplementedError('mpi4py package is not installed.')
        self._init_simulation(timesteps, dt, save_E)
        if file is not None and self._load(file):
            return
        mpi_comm = MPI.COMM_WORLD
        mpi_size = mpi_comm.Get_size()  # Number of MPI processes
        mpi_rank = mpi_comm.Get_rank()  # Rank of current MPI process
        process_dipoles = self.dipoles[mpi_rank::mpi_size]  # Dipoles evaluated
        disable_bar = not progressbar or mpi_rank != 0
        for tstep in tqdm(range(self.timesteps-1), total=self.timesteps,
                          initial=1, mininterval=0.5, disable=disable_bar):
            moment_data = []
            for dipole in process_dipoles:  # Only evaluate `process_dipoles`
                moment_disp, moment_vel = self._rk4(tstep, dipole)
                self._update_dipole(tstep, dipole, moment_disp, moment_vel,
                                    max_vel)
                moment_data.append((moment_disp, moment_vel))
            # Broadcast the dipole moment disp. and vel. to other MPI processes
            for bcast_rank in range(mpi_size):  # Send moment data
                if mpi_rank == bcast_rank:
                    mpi_comm.bcast(moment_data, root=bcast_rank)
                else:  # Receive moment data and update dipoles
                    bcast_data = None
                    bcast_data = mpi_comm.bcast(bcast_data, root=bcast_rank)
                    for dipole, data in zip(self.dipoles[bcast_rank::mpi_size],
                                            bcast_data):
                        self._update_dipole(tstep, dipole, data[0], data[1],
                                            max_vel)
        if mpi_rank == 0 and file is not None:
            self._save(file)

    def _init_simulation(self, timesteps, dt, save_E):
        self.timesteps = timesteps
        self.dt = dt
        self.save_E = save_E
        for dipole in self.dipoles:  # Initialize charges in dipole
            dipole.reset(timesteps, dt, save_E)
        if save_E:
            for dipole in self.dipoles:  # Initialize E driving field at t=0
                E_driving = self._E_driving(0, dipole, True)
                dipole.E_total[:, 0] = E_driving[0]
                dipole.E_vel[:, 0] = E_driving[1]
                dipole.E_acc[:, 0] = E_driving[2]

    def _rk4(self, t_step: int, dipole: Dipole) -> ndarray:
        """Perform RK4 method."""
        y = np.array((dipole.moment_disp[:, t_step],
                      dipole.moment_vel[:, t_step]))
        t = t_step*self.dt
        k1 = self.dt * self._LO_equation(t, y, dipole)
        k2 = self.dt * self._LO_equation(t+self.dt/2, y+k1/2, dipole)
        k3 = self.dt * self._LO_equation(t+self.dt/2, y+k2/2, dipole)
        k4 = self.dt * self._LO_equation(t+self.dt, y+k3, dipole)
        return y + 1/6*(k1 + 2*k2 + 2*k3 + k4)

    def _LO_equation(self, t: float, y: ndarray, dipole: Dipole) -> ndarray:
        """Calculate Lorentz oscillator equation of motion used by RK4."""
        E_driving = self._E_driving(t, dipole, False)
        dy = np.zeros((2, 3))
        dy[0, :] = y[1, :]
        dy[1, :] = (dipole.q/dipole.m_eff*E_driving
                    - dipole.gamma_0*y[1, :]
                    - dipole.omega_0**2*y[0, :])
        return dy

    def _E_driving(
        self,
        t: float,
        dipole: Dipole,
        return_all: bool
    ) -> Union[Tuple[ndarray, ndarray, ndarray], ndarray]:
        """Calculate the driving electric field experienced by `Dipole`."""
        x, y, z = np.meshgrid(*dipole.origin(t), indexing='ij')
        E_total = self.calculate_E(
            t=t, x=x, y=y, z=z, pcharge_field='Total',
            exclude_charges=dipole.charge_pair).flatten()
        if not return_all:
            return dipole.polar_dir * np.array(E_total)
        E_vel = self.calculate_E(t=t, x=x, y=y, z=z, pcharge_field='Velocity',
                                 exclude_charges=dipole.charge_pair).flatten()
        E_acc = self.calculate_E(t=t, x=x, y=y, z=z,
                                 pcharge_field='Acceleration',
                                 exclude_charges=dipole.charge_pair).flatten()
        return (dipole.polar_dir * np.array(E_total),
                dipole.polar_dir * np.array(E_vel),
                dipole.polar_dir * np.array(E_acc))

    def _update_dipole(
        self,
        tstep: int,
        dipole: Dipole,
        moment_disp: ndarray,
        moment_vel: ndarray,
        max_vel: float
    ) -> None:
        """Update the `Dipole` object's trajectory at each time step."""
        t = self.dt*(tstep+1)
        moment_acc = (moment_vel-dipole.moment_vel[:, tstep])/self.dt
        if self.save_E:
            E_driving = self._E_driving(t, dipole, True)
        else:
            E_driving = None
        dipole.update_timestep(moment_disp, moment_vel, moment_acc, E_driving)
        norm_vel = np.linalg.norm(dipole.charge_pair[0].velocity[:, tstep+1])
        if norm_vel > max_vel:
            print('Velocity larger than max_vel at timestep', tstep)
            raise ValueError('Velocity larger than max_vel!')


def combine_files(input_files: Tuple[str, ...], new_file: str) -> None:
    """Combine `Simulation` objects from many `.dat` files into a single file.

    Args:
        input_files: List of names of files to be concatenated.
        new_file: Name of output file, should end in `.dat`.
    """
    for file in input_files:
        with open(file, "rb") as f:
            loaded_simulation = pickle.load(f)
        with open(new_file, "ab") as new_f:
            pickle.dump(loaded_simulation, new_f)


def get_file_length(file: str) -> int:
    """Return the number of `Simulation` objects in `.dat` file.

    Args:
        file: File name.

    Returns:
        Number of `Simulation` objects in file, `-1` if file not found.
    """
    length = 0
    try:
        with open(file, "rb") as f:
            while True:
                pickle.load(f)
                length += 1
    except EOFError:
        return length
    except FileNotFoundError:
        return -1
