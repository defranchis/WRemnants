import narf
import narf.fitutils
import h5py
import numpy as np
import scipy
import tensorflow as tf
import tensorflow_probability as tfp

infile = "w_z_muonresponse_scetlib_dyturboCorr.hdf5"

hist_response = None

procs = []
procs.append("ZmumuPostVFP")
procs.append("ZtautauPostVFP")
procs.append("WplusmunuPostVFP")
procs.append("WminusmunuPostVFP")
procs.append("WplustaunuPostVFP")
procs.append("WminustaunuPostVFP")


with h5py.File(infile, 'r') as f:
    results = narf.ioutils.pickle_load_h5py(f["results"])
    for proc in procs:
        hist_response_proc = results[proc]["output"]["hist_qopr"].get()
        if hist_response is None:
            hist_response = hist_response_proc
        else:
            hist_response += hist_response_proc


print(hist_response)


hist_response = hist_response.project("genCharge", "qopr", "genPt", "genEta")

print(hist_response)

interp_sigmas = np.linspace(-3., 3., 9)
interp_cdfvals = 0.5*(1. + scipy.special.erf(interp_sigmas/np.sqrt(2.)))
interp_cdfvals = np.concatenate([[0.], interp_cdfvals, [1.]])

quant_cdfvals = tf.constant(interp_cdfvals, tf.float64)

quant_cdfvals = quant_cdfvals[None, :, None, None]

quants, errs = narf.fitutils.hist_to_quantiles(hist_response, quant_cdfvals, axis = 1)

print(quants[0, :, 0, 0])

quants = tf.constant(quants, tf.float64)
# quants = quants[..., None]

grid_points = [tf.constant(axis.centers) for axis in hist_response.axes]
grid_points = grid_points[2:]
grid_points = tuple(grid_points)


qopr_edges_flat = np.reshape(hist_response.axes[1].edges, [-1])
qopr_low = tf.constant(qopr_edges_flat[0], tf.float64)
qopr_high = tf.constant(qopr_edges_flat[-1], tf.float64)

def interp_cdf(genPt, genEta, genCharge, qopr):
    chargeIdx = tf.where(genCharge > 0., 1, 0)
    quants_charge = quants[chargeIdx]

    x = tf.stack([genPt, genEta], axis=0)
    x = x[None, :]
    quants_interp = tfp.math.batch_interp_rectilinear_nd_grid(x, x_grid_points = grid_points, y_ref = quants_charge, axis = 1)

    quants_interp = tf.reshape(quants_interp, [-1])
    quant_cdfvals_interp = tf.reshape(quant_cdfvals, [-1])

    qopr = tf.clip_by_value(qopr, qopr_low, qopr_high)

    qopr = tf.reshape(qopr, [-1])

    cdf = narf.fitutils.pchip_interpolate(xi = quants_interp, yi = quant_cdfvals_interp, x = qopr)

    return cdf

def interp_dweight(genPt, genEta, genCharge, qopr):
    with tf.GradientTape() as t0:
        t0.watch(qopr)
        with tf.GradientTape() as t1:
            t1.watch(qopr)
            cdf = interp_cdf(genPt, genEta, genCharge, qopr)
        pdf = t1.gradient(cdf, qopr)
    dpdf = t0.gradient(pdf, qopr)
    dweight = dpdf/pdf


    dweight = tf.where(qopr < qopr_low, tf.zeros_like(dweight), dweight)
    dweight = tf.where(qopr > qopr_high, tf.zeros_like(dweight), dweight)
    return dweight

genPt_test = tf.constant(25., tf.float64)
genEta_test = tf.constant(0.1, tf.float64)
genCharge_test = tf.constant(1., tf.float64)
qopr_test = tf.constant(1.002, tf.float64)

res = interp_cdf(genPt_test, genEta_test, genCharge_test, qopr_test)
res2 = interp_dweight(genPt_test, genEta_test, genCharge_test, qopr_test)

scalar_spec = tf.TensorSpec([], tf.float64)

class TestMod(tf.Module):
    @tf.function(input_signature =  [scalar_spec, scalar_spec, scalar_spec, scalar_spec])
    def __call__(self, genPt, genEta, genCharge, qopr):
        return interp_dweight(genPt, genEta, genCharge, qopr)

module = TestMod()

concrete_function = module.__call__.get_concrete_function()
# Convert the model
converter = tf.lite.TFLiteConverter.from_concrete_functions([concrete_function], module)

converter.target_spec.supported_ops = [
  tf.lite.OpsSet.TFLITE_BUILTINS, # enable TensorFlow Lite ops.
  tf.lite.OpsSet.SELECT_TF_OPS # enable TensorFlow ops.
]

tflite_model = converter.convert()

test_interp = tf.lite.Interpreter(model_content = tflite_model)
print(test_interp.get_input_details())
print(test_interp.get_output_details())
print(test_interp.get_signature_list())

# print(tflite_model)


with open('muon_response.tflite', 'wb') as f:
  f.write(tflite_model)

print(res)
print(res2)

