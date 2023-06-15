# Copyright (C) 2023  C-PAC Developers

# This file is part of C-PAC.

# C-PAC is free software: you can redistribute it and/or modify it under
# the terms of the GNU Lesser General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.

# C-PAC is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public
# License for more details.

# You should have received a copy of the GNU Lesser General Public
# License along with C-PAC. If not, see <https://www.gnu.org/licenses/>.
FROM ghcr.io/fcp-indi/c-pac/afni:23.0.07-bionic as AFNI
FROM ghcr.io/fcp-indi/c-pac/ants:2.4.3.python3.10-bionic as ANTs
FROM ghcr.io/fcp-indi/c-pac/c3d:1.0.0-bionic as c3d
FROM ghcr.io/fcp-indi/c-pac/connectome-workbench:1.5.0.neurodebian-bionic as connectome-workbench
FROM ghcr.io/fcp-indi/c-pac/fsl:6.0.6.4-python3.10-bionic as FSL
FROM ghcr.io/fcp-indi/c-pac/ica-aroma:0.4.4-beta-bionic as ICA-AROMA
FROM ghcr.io/fcp-indi/c-pac/msm:2.0-bionic as MSM

FROM ghcr.io/fcp-indi/c-pac/ubuntu:python3.10-bionic-non-free
LABEL org.opencontainers.image.description "NOT INTENDED FOR USE OTHER THAN AS A STAGE IMAGE IN A MULTI-STAGE BUILD \
Standard software dependencies for C-PAC standard and lite images"
LABEL org.opencontainers.image.source https://github.com/FCP-INDI/C-PAC
USER root

# Installing connectome-workbench
COPY --from=connectome-workbench /opt/workbench /opt/workbench
ENV PATH $PATH:/opt/workbench/bin_linux64

# Installing FSL
ENV FSLDIR=/usr/share/fsl/6.0 \
    FSLOUTPUTTYPE=NIFTI_GZ \
    FSLMULTIFILEQUIT=TRUE \
    FSLTCLSH=/usr/bin/tclsh \
    FSLWISH=/usr/bin/wish \
    TZ=America/New_York
ENV POSSUMDIR=${FSLDIR}/6.0 \
    LD_LIBRARY_PATH=${FSLDIR}/6.0:$LD_LIBRARY_PATH \
    PATH=${FSLDIR}/bin:$PATH
COPY --from=FSL /usr/bin/tclsh /usr/bin/tclsh
COPY --from=FSL /usr/bin/wish /usr/bin/wish
COPY --from=FSL /usr/share/fsl/ /usr/share/fsl/
COPY --from=FSL /lib/x86_64-linux-gnu/lib*so* /lib/x86_64-linux-gnu/

# Installing and setting up c3d
COPY --from=c3d /opt/c3d/ opt/c3d/
ENV C3DPATH /opt/c3d/
ENV PATH $C3DPATH/bin:$PATH

# Installing AFNI
COPY --from=AFNI /lib/x86_64-linux-gnu/ld* /lib/x86_64-linux-gnu/
COPY --from=AFNI /lib/x86_64-linux-gnu/lib*so* /lib/x86_64-linux-gnu/
COPY --from=AFNI /lib64/ld* /lib64/
COPY --from=AFNI /opt/afni/ /opt/afni/
COPY --from=AFNI /usr/lib/x86_64-linux-gnu/lib*so* /usr/lib/x86_64-linux-gnu/
# set up AFNI
ENV PATH=/opt/afni:$PATH

# Installing ANTs
ENV PATH=/usr/lib/ants/bin:$PATH
COPY --from=ANTs /usr/lib/ants/ /usr/lib/ants/
COPY --from=ANTs /ants_template/ /ants_template/

# Installing ICA-AROMA
COPY --from=ICA-AROMA /opt/ICA-AROMA/ /opt/ICA-AROMA/
ENV PATH=/opt/ICA-AROMA:$PATH

# install Multimodal Surface Matching
COPY --from=MSM /opt/msm/Ubuntu/msm /opt/msm/Ubuntu/msm
ENV MSMBINDIR=/opt/msm/Ubuntu \
    PATH=$PATH:/opt/msm/Ubuntu

# link libraries & clean up
RUN rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* && \
    ldconfig && \
    chmod 777 / && \
    chmod 777 $(ls / | grep -v sys | grep -v proc)

# set user
USER c-pac_user
