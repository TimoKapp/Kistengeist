# shellcheck shell=bash
# Cowork: virtuelle Maschine über QEMU/KVM (laut Anthropic-Doku für arm64).

# Mit Empfehlungen (z. B. qemu-utils, ipxe-qemu) – so wie claude-desktop sie laut Anthropic mitzieht.
cp_apt_install qemu-system-arm qemu-efi-aarch64 virtiofsd
cp_run usermod -aG kvm "$CP_USER"
printf 'vhost_vsock\n' | cp_write /etc/modules-load.d/vhost_vsock.conf
cp_run modprobe vhost_vsock || cp_warn "Kernelmodul vhost_vsock fehlt – Cowork wird vermutlich nicht starten."
if [ "$CP_DRY_RUN" != "1" ] && [ ! -e /dev/kvm ]; then
    cp_warn "/dev/kvm fehlt – der Kernel bietet keine Virtualisierung; Cowork wird nicht starten."
fi
