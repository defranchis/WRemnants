from utilities import common, logging
from utilities.io_tools import input_tools

import numpy as np

logger = logging.child_logger(__name__)

def add_recoil_uncertainty(card_tool, samples, passSystToFakes=False, pu_type="highPU", flavor="", group_compact=True):
    met = input_tools.args_from_metadata(card_tool, "met")
    if flavor == "":
        flavor = input_tools.args_from_metadata(card_tool, "flavor")
    if pu_type == "highPU" and (met in ["RawPFMET", "DeepMETReso"]):

        card_tool.addSystematic("recoil_stat",
            processes=samples,
            mirror = True,
            group = "recoil" if group_compact else "recoil_stat",
            splitGroup={"experimental": f".*"},
            systAxes = ["recoil_unc"],
            passToFakes=passSystToFakes,
        )

        card_tool.addSystematic("recoil_syst",
            processes=samples,
            mirror = True,
            group = "recoil" if group_compact else "recoil_syst",
            splitGroup={"experimental": f".*"},
            systAxes = ["recoil_unc"],
            passToFakes=passSystToFakes,
        )

def projectABCD(cardTool, h, return_variances=False, dtype="float64"):
    # in case the desired axes are different at low MT and high MT we need to project each seperately, and then concatenate

    if any(ax not in h.axes.name for ax in cardTool.fakerateAxes):
        logger.warning(f"Not all desired fakerate axes found in histogram. Fakerate axes are {cardTool.fakerateAxes}, and histogram axes are {h.axes.name}")

    fakerate_axes = [n for n in h.axes.name if n in cardTool.fakerateAxes]

    lowMT_axes = [n for n in h.axes.name if n in fakerate_axes]
    highMT_failIso_axes = [n for n in h.axes.name if n in [*fakerate_axes, *cardTool.fit_axes]]
    highMT_passIso_axes = [n for n in h.axes.name if n in cardTool.fit_axes]

    hist_lowMT = h[{cardTool.nameMT : cardTool.failMT}].project(*[*lowMT_axes, common.passIsoName])
    hist_highMT_failIso = h[{cardTool.nameMT : cardTool.passMT, **common.failIso}].project(*[*highMT_failIso_axes])
    hist_highMT_passIso = h[{cardTool.nameMT : cardTool.passMT, **common.passIso}].project(*[*highMT_passIso_axes])

    flat_lowMT = hist_lowMT.values(flow=False).flatten().astype(dtype)
    flat_highMT_failIso = hist_highMT_failIso.values(flow=False).flatten().astype(dtype)
    flat_highMT_passIso = hist_highMT_passIso.values(flow=False).flatten().astype(dtype)

    flat = np.append(flat_lowMT, flat_highMT_failIso)
    flat = np.append(flat, flat_highMT_passIso)

    if not return_variances:
        return flat

    flat_variances_lowMT = hist_lowMT.variances(flow=False).flatten().astype(dtype)
    flat_variances_highMT_failIso = hist_highMT_failIso.variances(flow=False).flatten().astype(dtype)
    flat_variances_highMT_passIso = hist_highMT_passIso.variances(flow=False).flatten().astype(dtype)

    flat_variances = np.append(flat_variances_lowMT, flat_variances_highMT_failIso)
    flat_variances = np.append(flat_variances, flat_variances_highMT_passIso)

    return flat, flat_variances


