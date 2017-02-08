"""
Sandbox target selection cuts, intended for algorithms that are still in
development.

"""
import os.path
from time import time

import numpy as np
from astropy.table import Table, Row

import desitarget.targets
from desitarget.cuts import unextinct_fluxes, _is_row
from desitarget.internal import sharedmem
from desitarget import desi_mask, bgs_mask, mws_mask

def isLRG_2016v3_colors(gflux=None, rflux=None, zflux=None, w1flux=None,
                        w2flux=None, ggood=None, primary=None): 

    """See the isLRG_2016v3() function for details.  This function applies just the
       flux and color cuts.

    """
    if primary is None:
        primary = np.ones_like(rflux, dtype='?')
        lrg = primary.copy()

    if ggood is None:
        ggood = np.ones_like(gflux, dtype='?')

    # Basic flux and color cuts
    lrg = primary.copy()
    lrg &= (zflux > 10**(0.4*(22.5-20.4))) # z<20.4
    lrg &= (zflux < 10**(0.4*(22.5-18))) # z>18
    lrg &= (zflux < 10**(0.4*2.5)*rflux) # r-z<2.5
    lrg &= (zflux > 10**(0.4*0.8)*rflux) # r-z>0.8

    # This is the star-galaxy separation cut
    # Wlrg = (z-W)-(r-z)/3 + 0.3 >0 , which is equiv to r+3*W < 4*z+0.9
    lrg &= (rflux*w1flux**3 > (zflux**4)*10**(-0.4*0.9))

    # Now for the work-horse sliding flux-color cut:
    # mlrg2 = z-2*(r-z-1.2) < 19.6 -> 3*z < 19.6-2.4-2*r
    lrg &= (zflux**3 > 10**(0.4*(22.5+2.4-19.6))*rflux**2)

    # Another guard against bright & red outliers
    # mlrg2 = z-2*(r-z-1.2) > 17.4 -> 3*z > 17.4-2.4-2*r
    lrg &= (zflux**3 < 10**(0.4*(22.5+2.4-17.4))*rflux**2)

    # Finally, a cut to exclude the z<0.4 objects while retaining the elbow at
    # z=0.4-0.5.  r-z>1.2 || (good_data_in_g and g-r>1.7).  Note that we do not
    # require gflux>0.
    lrg &= np.logical_or((zflux > 10**(0.4*1.2)*rflux), (ggood & (rflux>10**(0.4*1.7)*gflux)))

    return lrg

def isLRG_2016v3(gflux=None, rflux=None, zflux=None, w1flux=None,
                 rflux_snr=None, zflux_snr=None, w1flux_snr=None,
                 gflux_ivar=None, primary=None): 

    """This is version 3 of the Eisenstein/Dawson Summer 2016 work on LRG target
    selection, but anymask has been changed to allmask, which probably means
    that the flux cuts need to be re-tuned.  That is, mlrg2<19.6 may need to
    change to 19.5 or 19.4.
      -Daniel Eisenstein -- Jan 9, 2017

    Args:
      gflux, 

    # Inputs: decam_flux, decam_flux_ivar, decam_allmask, decam_mw_transmission
    # wise_flux, wise_flux_ivar, wise_mw_transmission
    # Using g, r, z, and W1 information.

    # Applying the reddening
    # Also clip r, z, and W1 at 0 to avoid warnings from negative numbers raised to
    # fractional powers.  

    """
    if primary is None:
        primary = np.ones_like(rflux, dtype='?')
        lrg = primary.copy()

    # Some basic quality in r, z, and W1.  Note by @moustakas: no allmask cuts
    # used!).  Also note: We do not require gflux>0!  Objects can be very red.
    lrg = primary.copy()
    lrg &= (rflux_snr > 0) # and rallmask == 0
    lrg &= (zflux_snr > 0) # and zallmask == 0
    lrg &= (w1flux_snr > 4)
    lrg &= (rflux > 0)
    lrg &= (zflux > 0)

    ggood = (gflux_ivar > 0) # and gallmask == 0

    # Apply color, flux, and star-galaxy separation cuts.
    lrg &= isLRG_2016v3_colors(gflux=gflux, rflux=rflux, zflux=zflux,
                               w1flux=w1flux, ggood=ggood, primary=primary)

    return lrg

def apply_sandbox_cuts(objects):
    """Perform target selection on objects, returning target mask arrays

    Args:
        objects: numpy structured array with UPPERCASE columns needed for
            target selection, OR a string tractor/sweep filename

    Returns:
        (desi_target, bgs_target, mws_target) where each element is
        an ndarray of target selection bitmask flags for each object
        
    Bugs:
        If objects is a astropy Table with lowercase column names, this
        converts them to UPPERCASE in-place, thus modifying the input table.
        To avoid this, pass in objects.copy() instead. 

    See desitarget.targetmask for the definition of each bit

    """
    #- Check if objects is a filename instead of the actual data
    if isinstance(objects, str):
        from desitarget import io
        objects = io.read_tractor(objects)
    
    #- ensure uppercase column names if astropy Table
    if isinstance(objects, (Table, Row)):
        for col in list(objects.columns.values()):
            if not col.name.isupper():
                col.name = col.name.upper()

    #- undo Milky Way extinction
    flux = unextinct_fluxes(objects)
    gflux = flux['GFLUX']
    rflux = flux['RFLUX']
    zflux = flux['ZFLUX']
    w1flux = flux['W1FLUX']
    w2flux = flux['W2FLUX']
    objtype = objects['TYPE']
    
    decam_ivar = objects['DECAM_FLUX_IVAR']
    decam_snr = objects['DECAM_FLUX'] * np.sqrt(objects['DECAM_FLUX_IVAR'])
    wise_snr = objects['WISE_FLUX'] * np.sqrt(objects['WISE_FLUX_IVAR'])

    #- DR1 has targets off the edge of the brick; trim to just this brick
    try:
        primary = objects['BRICK_PRIMARY']
    except (KeyError, ValueError):
        if _is_row(objects):
            primary = True
        else:
            primary = np.ones_like(objects, dtype=bool)
        
    lrg = isLRG_2016v3(gflux=gflux, rflux=rflux, zflux=zflux, w1flux=w1flux,
                       gflux_ivar=decam_ivar[..., 1], 
                       rflux_snr=decam_snr[..., 2],
                       zflux_snr=decam_snr[..., 4],
                       w1flux_snr=wise_snr[..., 0],
                       primary=primary)

    #- construct the targetflag bits
    #- Currently our only cuts are DECam based (i.e. South)
    desi_target  = lrg * desi_mask.LRG_SOUTH
    #desi_target |= elg * desi_mask.ELG_SOUTH
    #desi_target |= qso * desi_mask.QSO_SOUTH

    desi_target |= lrg * desi_mask.LRG
    #desi_target |= elg * desi_mask.ELG
    #desi_target |= qso * desi_mask.QSO

    #desi_target |= fstd * desi_mask.STD_FSTAR

    bgs_target = np.zeros_like(desi_target)
    #bgs_target = bgs_bright * bgs_mask.BGS_BRIGHT
    #bgs_target |= bgs_bright * bgs_mask.BGS_BRIGHT_SOUTH
    #bgs_target |= bgs_faint * bgs_mask.BGS_FAINT
    #bgs_target |= bgs_faint * bgs_mask.BGS_FAINT_SOUTH

    #- nothing for MWS yet; will be GAIA-based
    #if isinstance(bgs_target, numbers.Integral):
    #    mws_target = 0
    #else:
    #    mws_target = np.zeros_like(bgs_target)
    mws_target = np.zeros_like(desi_target)

    #- Are any BGS or MWS bit set?  Tell desi_target too.
    desi_target |= (bgs_target != 0) * desi_mask.BGS_ANY
    desi_target |= (mws_target != 0) * desi_mask.MWS_ANY

    return desi_target, bgs_target, mws_target





def apply_XD_globalerror(objs, last_FoM, glim=23.8, rlim=23.4, zlim=22.4, gr_ref=0.5,\
                       rz_ref=0.5,reg_r=1e-4/(0.025**2 * 0.05),f_i=[1., 1., 0., 0.25, 0., 0.25, 0.],\
                       gmin = 21., gmax = 24.):
    """ Apply ELG XD selection. Default uses fiducial set of parameters.

    Args:
        objs: A DECaLS fits table.
        last_FoM: Threshold FoM.
        
    Optional:
        glim, rlim, zlim: 5-sigma detection limiting magnitudes. 
        gr_ref, rz_ref: Number density conserving global error reference point.
        reg_r: Regularization parameter. Empirically set to avoid pathologic 
            behaviors of the selection boundary.
        f_i: Various class weights for FoM.
        gmin, gmax: Minimum and maximum g-magnitude range to consider.

    
    Returns:
        iXD: Boolean mask array that implements XD selection.
        FoM: Figure of Merit number computed for objects that pass the initial set of masks.

    Note:
        1. The current version of XD selection method assumes the imposition of decam_allmask 
            and tycho2 stellar mask. (The individual class densities have been fitted with these 
            masks imposed.) However, the code does not implement them yet as we want to understand
            the large scale systematics of the XD selection with and without these masks.
        2. A different  version of this function using individual Tractor error is called 
            apply_XD_Tractor_error().
            
        Process in summary:
            - Construct a Python dictionary that contains all XD GMM and dNdm parameters
                using a string.
            - Load variables from the input astropy fits table.
            - Compute which objects pass the reasonable imaging quality cut 
                (SNR>2, flux positive, and flux invariance positive).
            - Compute which objects pass a rough color cut that eliminates a
                bulk of low redshift contaiminants. 
            - For each object that passes the above two cuts, compute Figure of Merit FoM.
            - If FoM>FoM_last, then include the object in the selection.
            - Append this selection column to the table and return.

    """
    ####### Density parameters hard coded in. np.float64 used for maximal precision. #######
    params ={(0, 'mean'): np.array([[ 0.374283820390701,  1.068873405456543],
           [ 0.283886760473251,  0.733299076557159]]),
    (1, 'mean'): np.array([[ 0.708186626434326,  1.324055671691895],
           [ 0.514687597751617,  0.861691951751709]]),
    (2, 'mean'): np.array([[ 0.851126551628113,  1.49790346622467 ],
           [ 0.593997478485107,  1.027981519699097]]),
    (3, 'mean'): np.array([[ 0.621764063835144,  0.677076101303101],
           [ 1.050391912460327,  1.067378640174866]]),
    (4, 'mean'): np.array([[ 0.29889178276062 ,  0.158586874604225],
           [ 0.265404641628265,  0.227356120944023],
           [ 1.337790369987488,  1.670260787010193]]),
    (5, 'mean'): np.array([[ 0.169899195432663,  0.333086401224136],
           [ 0.465608537197113,  0.926179945468903]]),
    (6, 'mean'): np.array([[ 0.404752403497696,  0.157505303621292],
           [ 1.062281489372253,  0.708624482154846],
           [ 0.767854988574982,  0.410259902477264],
           [ 1.830820441246033,  1.096370458602905],
           [ 1.224291563034058,  0.748376846313477],
           [ 0.623223185539246,  0.588687479496002],
           [ 1.454894185066223,  1.615718483924866]]),
    (0, 'amp'): np.array([ 0.244611976587951,  0.755388023412049]),
    (1, 'amp'): np.array([ 0.114466286005043,  0.885533713994957]),
    (2, 'amp'): np.array([ 0.138294309756769,  0.861705690243231]),
    (3, 'amp'): np.array([ 0.509696013263716,  0.490303986736284]),
    (4, 'amp'): np.array([ 0.264565190839574,  0.464308147030861,  0.271126662129565]),
    (5, 'amp'): np.array([ 0.803360982047185,  0.196639017952815]),
    (6, 'amp'): np.array([ 0.09128923215233 ,  0.254327925723203,  0.31780750840433 ,
            0.036144574976436,  0.145786317010496,  0.031381535653226,
            0.12326290607998 ]),
    (0, 'covar'): np.array([[[ 0.10418130703232 ,  0.014280057648813],
            [ 0.014280057648813,  0.070314900027689]],

           [[ 0.023818843706279,  0.018202660741959],
            [ 0.018202660741959,  0.041376141039073]]]),
    (1, 'covar'): np.array([[[ 0.215211984773353,  0.054615838823342],
            [ 0.054615838823342,  0.049833562813203]],

           [[ 0.04501376209018 ,  0.017654245897094],
            [ 0.017654245897094,  0.036243604905033]]]),
    (2, 'covar'): np.array([[[ 0.393998394239911,  0.08339271763515 ],
            [ 0.08339271763515 ,  0.043451758548033]],

           [[ 0.104132127558071,  0.066660191134385],
            [ 0.066660191134385,  0.099474014771686]]]),
    (3, 'covar'): np.array([[[ 0.077655250186381,  0.048031436118266],
            [ 0.048031436118266,  0.104180325930248]],

           [[ 0.18457377102254 ,  0.13405411581603 ],
            [ 0.13405411581603 ,  0.11061389825436 ]]]),
    (4, 'covar'): np.array([[[ 0.004346580392509,  0.002628470120243],
            [ 0.002628470120243,  0.003971775282994]],

           [[ 0.048642690792318,  0.010716631911343],
            [ 0.010716631911343,  0.061199277021983]],

           [[ 0.042759461532687,  0.038563281355028],
            [ 0.038563281355028,  0.136138353942557]]]),
    (5, 'covar'): np.array([[[ 0.016716270750336, -0.002912143075387],
            [-0.002912143075387,  0.048058573349518]],

           [[ 0.162280075685762,  0.056056904861885],
            [ 0.056056904861885,  0.123029790628176]]]),
    (6, 'covar'): np.array([[[ 0.008867550173445,  0.005830414294608],
            [ 0.005830414294608,  0.004214767113419]],

           [[ 0.128202602012536,  0.102774200195474],
            [ 0.102774200195474,  0.103174267985407]],

           [[ 0.040911683088027,  0.017665837401128],
            [ 0.017665837401128,  0.013744306762296]],

           [[ 0.007956756372728,  0.01166041211521 ],
            [ 0.01166041211521 ,  0.030148938891721]],

           [[ 0.096468861178697,  0.036857159884246],
            [ 0.036857159884246,  0.016938035737711]],

           [[ 0.112556609450265, -0.027450040449295],
            [-0.027450040449295,  0.108044495426867]],

           [[ 0.008129216729562,  0.026162239500016],
            [ 0.026162239500016,  0.163188167512441]]]),
    (0, 'dNdm'): np.array([  4.192577862669580e+00,   2.041560039425720e-01,
             5.211356980204467e-01,   1.133059580454155e+03]),
    (1, 'dNdm'): np.array([  3.969155875747644e+00,   2.460106047909254e-01,
             7.649675390577662e-01,   1.594000900095526e+03]),
    (2, 'dNdm'): np.array([ -2.75804468990212 ,  84.684286895340932]),
    (3, 'dNdm'): np.array([   5.366276446077002,    0.931168472808592,    1.362372397828176,
            159.580421075961794]),
    (4, 'dNdm'): np.array([  -0.415601564925459,  125.965707251899474]),
    (5, 'dNdm'): np.array([  -2.199904276713916,  206.28117629545153 ]),
    (6, 'dNdm'): np.array([  8.188847496561811e-01,  -4.829571612433957e-01,
             2.953829284553960e-01,   1.620279479977582e+04])
    }

    # ####### Load paramters - method 2. Rather than hardcoding in the parameters,
    # we could also import them from a file ######
    # def generate_XD_model_dictionary(tag1="glim24", tag2="", K_i = [2,2,2,2,3,2,7], dNdm_type = [1, 1, 0, 1, 0, 0, 1]):
    #     # Create empty dictionary
    #     params = {}
        
    #     # Adding dNdm parameters for each class
    #     for i in range(7):
    #         if dNdm_type[i] == 0:
    #             dNdm_params =np.loadtxt(("%d-fit-pow-"+tag1)%i)
    #         else:
    #             dNdm_params =np.loadtxt(("%d-fit-broken-"+tag1)%i)
    #         params[(i, "dNdm")] = dNdm_params
            
    #     # Adding GMM parameters for each class
    #     for i in range(7):
    #         amp, mean, covar = load_params_XD(i,K_i[i],tag0="fit",tag1=tag1,tag2=tag2)
    #         params[(i,"amp")] = amp
    #         params[(i,"mean")] = mean
    #         params[(i,"covar")] = covar
            
    #     return params

    # def load_params_XD(i,K,tag0="fit",tag1="glim24",tag2=""):
    #     fname = ("%d-params-"+tag0+"-amps-"+tag1+"-K%d"+tag2+".npy") %(i, K)
    #     amp = np.load(fname)
    #     fname = ("%d-params-"+tag0+"-means-"+tag1+"-K%d"+tag2+".npy") %(i, K)
    #     mean= np.load(fname)
    #     fname = ("%d-params-"+tag0+"-covars-"+tag1+"-K%d"+tag2+".npy") %(i, K)
    #     covar  = np.load(fname)
    #     return amp, mean, covar        

    # params = generate_XD_model_dictionary()



    ####### Load variables. #######
    # Flux
    gflux = objs['decam_flux'][:][:,1]/objs['decam_mw_transmission'][:][:,1] 
    rflux = objs['decam_flux'][:][:,2]/objs['decam_mw_transmission'][:][:,2]
    zflux = objs['decam_flux'][:][:,4]/objs['decam_mw_transmission'][:][:,4]
    # mags
    g = (22.5 - 2.5*np.log10(gflux)) 
    r = (22.5 - 2.5*np.log10(rflux))
    z = (22.5 - 2.5*np.log10(zflux))    
    # Inver variance
    givar = objs['decam_flux_ivar'][:][:,1]
    rivar = objs['decam_flux_ivar'][:][:,2]
    zivar = objs['decam_flux_ivar'][:][:,4]
    # Color
    rz = (r-z); gr = (g-r)    
    

    ####### Reaonsable quaity cut. #######
    iflux_positive = (gflux>0)&(rflux>0)&(zflux>0)
    ireasonable_color = (gr>-0.5) & (gr<2.5) & (rz>-0.5) &(rz<2.7) & (g<gmax) & (g>gmin)
    thres = 2
    igrz_SN2 =  ((gflux*np.sqrt(givar))>thres)&((rflux*np.sqrt(rivar))>thres)&((zflux*np.sqrt(zivar))>thres)
    # Combination of above cuts.
    ireasonable = iflux_positive & ireasonable_color & igrz_SN2
    
    ####### A rough cut #######
    irough = (gr<1.3) & np.logical_or(gr<(rz+0.3) ,gr<0.3)

    ####### Objects for which FoM to be calculated. #######
    ibool = ireasonable & irough 
    
    ######## Compute FoM values for objects that pass the cuts. #######
    # Place holder for FoM
    FoM = np.zeros(ibool.size, dtype=np.float)

    # Select subset of objects.
    mag = g[ibool]
    flux = gflux[ibool]    
    gr = gr[ibool]
    rz = rz[ibool]

    # Compute the global error noise corresponding to each objects.
    const = 2.5/(5*np.log(10)) 
    gvar = (const * 10**(0.4*(mag-glim)))**2
    rvar = (const * 10**(0.4*(mag-gr_ref-rlim)))**2
    zvar = (const * 10**(0.4*(mag-gr_ref-rz_ref-zlim)))**2        

    # Calculate the densities.
    # Helper function 1.
    def GMM_vectorized(gr, rz, amps, means, covars, gvar, rvar, zvar):
        """
        Color-color density    

        Params
        ------
        gvar, rvar, zvar: Pre-computed errors based on individual grz values scaled from 5-sigma detection limits.
        """
        # Place holder for return array.
        density = np.zeros(gr.size,dtype=np.float)
        
        # Compute 
        for i in range(amps.size):
            # Calculating Sigma+Error
            C11 = covars[i][0,0]+gvar+rvar
            C12 = covars[i][0,1]+rvar
            C22 = covars[i][1,1]+rvar+zvar
            
            # Compute the determinant
            detC = C11*C22-C12**2
            
            # Compute variables
            x11 = (gr-means[i][0])**2
            x12 = (gr-means[i][0])*(rz-means[i][1])
            x22 = (rz-means[i][1])**2
            
            # Calculating the exponetial
            EXP = np.exp(-(C22*x11-2*C12*x12+C11*x22)/(2.*detC+1e-12))
            
            density += amps[i]*EXP/(2*np.pi*np.sqrt(detC)+1e-12)
        
        return density


    # Helper function 2.
    def dNdm(params, flux):
        num_params = params.shape[0]
        if num_params == 2:
            return pow_law(params, flux)
        elif num_params == 4:
            return broken_pow_law(params, flux)

    # Helper function 3.
    def pow_law(params, flux):
        A = params[1]
        alpha = params[0]
        return A* flux**alpha

    # Helper function 4.
    def broken_pow_law(params, flux):
        alpha = params[0]
        beta = params[1]
        fs = params[2]
        phi = params[3]
        return phi/((flux/fs)**alpha+(flux/fs)**beta + 1e-12)
 
    FoM_num = np.zeros_like(gr)
    FoM_denom = np.zeros_like(gr)
    for i in range(7): # number of classes.
        n_i = GMM_vectorized(gr,rz, params[i, "amp"], params[i, "mean"],params[i, "covar"], gvar, rvar, zvar)  * dNdm(params[(i,"dNdm")], flux)
        FoM_num += f_i[i]*n_i
        FoM_denom += n_i
           
    FoM[ibool] = FoM_num/(FoM_denom+reg_r+1e-12) # For proper broadcasting.
    
    # XD-selection
    iXD = FoM>last_FoM
    
    return iXD, FoM


