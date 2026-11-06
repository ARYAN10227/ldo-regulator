* ---- LDO core: error amp + PMOS pass device + feedback divider ----
* Nodes: vin (input), out (output), fbx (divider tap), ein (error-amp + input)
.param RESR=0.5 COUT=4.7u ROEA=200 ADC=10k AHF=100 FZ=2k FP1=100k
VREF ref 0 1.2
* Error amplifier: 80 dB at DC, lag-lead to 40 dB above FZ, pole at FP1, driver referenced to VIN
.param RHF=10k RDC={RHF*ADC/AHF}
GEA 0 ea1 ref ein {AHF/RHF}
RDC ea1 0 {RDC}
RHF ea1 ez {RHF}
CZ ez 0 {1/(2*3.14159265*FZ*RHF)}
CP ea1 0 {1/(2*3.14159265*FP1*RHF)}
* Gate driver referenced to VIN: gate = VIN - drive, so input ripple does not change Vsg
BEA ea2 0 V = V(vin) - min(max(V(ea1),0),V(vin))
ROEA ea2 gate {ROEA}
* Pass device: power PMOS (Vt = -1 V, ~1 nF gate)
MP out gate vin vin PPASS W=8m L=2u
.model PPASS PMOS(LEVEL=1 VTO=-1 KP=50u LAMBDA=0.02 CGSO=1.2e-7 CGDO=2.5e-8)
* Feedback divider: Vout = 1.2 V x (1 + 174k/100k) = 3.288 V
RF1 out fbx 174k
RF2 fbx 0 100k
* Output capacitor with ESR
COUT out cesr {COUT}
RESR cesr 0 {RESR}
