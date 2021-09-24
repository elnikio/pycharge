"""Plot sinusoidal plane wave electric field along x direction."""
# pragma pylint: disable=unexpected-keyword-arg, W0621, W0613
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import SymLogNorm
from mpl_toolkits.axes_grid1.inset_locator import inset_axes
from scipy.constants import c
import pycharge as pc


def E_field(t, x, y, z):
    """Return sinusoidal plane wave electric field along x direction."""
    return [1e8*np.sin(2*np.pi/wavelength*(x-c*t)), 0, 0]


dt = 1e-18
wavelength = 10e-9

simulation = pc.Simulation([], E_field)  # No charges in simulation

# Create meshgrid in x-y plane between -10 nm to 10 nm at z=0
lim = 10e-9
npoints = 1000  # Number of grid points
coordinates = np.linspace(-lim, lim, npoints)  # grid from -lim to lim
x, y, z = np.meshgrid(coordinates, coordinates, 0, indexing='ij')  # z=0

# Calculate E field components at t=0
E_x, E_y, E_z = simulation.calculate_E(t=0, x=x, y=y, z=z)

# Plot E_x, E_y, and E_z fields
E_x_plane = E_x[:, :, 0]  # Create 2D array at z=0 for plotting
E_y_plane = E_y[:, :, 0]
E_z_plane = E_z[:, :, 0]

# Create figs and axes, plot E components on log scale
fig, axs = plt.subplots(1, 3, sharey=True)
norm = SymLogNorm(linthresh=1.01e6, linscale=1, vmin=-1e9, vmax=1e9)
extent = [-lim, lim, -lim, lim]
im_0 = axs[0].imshow(E_x_plane.T, origin='lower', norm=norm, extent=extent)
im_1 = axs[1].imshow(E_y_plane.T, origin='lower', norm=norm, extent=extent)
im_2 = axs[2].imshow(E_z_plane.T, origin='lower', norm=norm, extent=extent)

# Add labels
for ax in axs:
    ax.set_xlabel('x (nm)')
axs[0].set_ylabel('y (nm)')
axs[0].set_title('E_x')
axs[1].set_title('E_y')
axs[2].set_title('E_z')

# Add colorbar to figure
Ecax = inset_axes(axs[2],
                  width="6%",  # width = 5% of parent_bbox width
                  height="100%",  # height : 50%
                  loc='lower left',
                  bbox_to_anchor=(1.05, 0., 1, 1),
                  bbox_transform=axs[2].transAxes,
                  borderpad=0,
                  )
E_cbar = plt.colorbar(im_2, cax=Ecax)  # right of im_2
E_cbar.ax.set_ylabel('E (N/C)', rotation=270, labelpad=12)

plt.show()
