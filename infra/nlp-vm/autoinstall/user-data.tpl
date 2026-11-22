#cloud-config
autoinstall:
  version: 1
  refresh-installer:
    update: false
  locale: en_US.UTF-8
  timezone: Asia/Tokyo
  identity:
    hostname: keiba-nlp
    username: nlp
    password: '{{PASSWORD_HASH}}'
  ssh:
    install-server: true
    authorized-keys:
      - '{{SSH_PUBLIC_KEY}}'
    allow-pw: false
  early-commands:
    - timeout 600 sh -c 'until test -e /run/keiba-nlp-recovery-ready; do sleep 1; done'
    - test "$(blockdev --getsize64 /dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0)" = 107374182400
  network:
    version: 2
    ethernets:
      enp0s17:
        match:
          macaddress: '00:0c:29:3a:81:3b'
        dhcp4: false
        dhcp6: false
        addresses: [192.168.0.14/24]
        routes:
          - to: default
            via: 192.168.0.1
        nameservers:
          addresses: [192.168.0.1]
  storage:
    layout:
      name: lvm
      sizing-policy: all
      match:
        id_path: pci-0000:00:10.0-scsi-0:0:0:0
  apt:
    geoip: false
    mirror-selection:
      primary:
        - uri: https://archive.ubuntu.com/ubuntu
    fallback: abort
  packages:
    - openssh-server
    - open-vm-tools
    - chrony
    - ufw
    - podman
  shutdown: poweroff
