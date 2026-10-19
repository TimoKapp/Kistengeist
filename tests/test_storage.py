import kistengeist_storage as st


def test_parse_mounts_filters_and_unescapes():
    text = (
        "/dev/mmcblk0p2 / ext4 rw 0 0\n"
        "proc /proc proc rw 0 0\n"
        "/dev/mmcblk0p1 /boot/firmware vfat rw 0 0\n"
        "/dev/sda1 /media/claude/MEIN\\040STICK vfat rw 0 0\n"
        "tmpfs /run tmpfs rw 0 0\n"
    )
    mounts = st.parse_mounts(text)
    assert ("/dev/sda1", "/media/claude/MEIN STICK", "vfat") in mounts
    assert all(m[2] != "proc" and m[2] != "tmpfs" for m in mounts)
    assert len(mounts) == 3


def test_labels_and_warnings():
    root = st.Mount("/dev/mmcblk0p2", "/", "ext4", 100, 95, 5, False)
    usb = st.Mount("/dev/sda1", "/media/claude/STICK", "vfat", 100, 10, 90, True)
    boot = st.Mount("/dev/mmcblk0p1", "/boot/firmware", "vfat", 100, 99, 1, False)
    assert root.label.startswith("System")
    assert usb.label == "USB: STICK"
    warns = st.warnings([root, usb, boot])
    assert len(warns) == 1 and "95 %" in warns[0]


def test_parent_device():
    assert st.parent_device("/dev/sda1") == "/dev/sda"
    assert st.parent_device("/dev/mmcblk0p1") == "/dev/mmcblk0"
    assert st.parent_device("/dev/nvme0n1p2") == "/dev/nvme0n1"


def test_human():
    assert st.human(512) == "512 B"
    assert st.human(1536) == "1,5 KB"
    assert st.human(3 * 1024**3) == "3,0 GB"


def test_meminfo():
    info = st.parse_meminfo("MemTotal:  8000 kB\nMemAvailable: 6000 kB\nFoo: bar\n")
    assert info == {"MemTotal": 8000 * 1024, "MemAvailable": 6000 * 1024}


def test_clear_cache_and_largest(tmp_path):
    cache = tmp_path / ".cache" / "chromium"
    (cache / "sub").mkdir(parents=True)
    (cache / "sub" / "a.bin").write_bytes(b"x" * 50000)
    (cache / "b.bin").write_bytes(b"y" * 50000)
    assert st.cache_dirs(str(tmp_path)) == [str(cache)]
    largest = st.largest_entries(str(tmp_path))
    assert largest[0][0] == str(tmp_path / ".cache")
    freed = st.clear_dir_contents(str(cache))
    assert freed > 0
    assert cache.is_dir() and not any(cache.iterdir())


def test_parent_device_via_sysfs(tmp_path):
    disk = tmp_path / "devices" / "sda"
    (disk / "sda1").mkdir(parents=True)
    (disk / "sda1" / "partition").write_text("1")
    cls = tmp_path / "class"
    cls.mkdir()
    (cls / "sda").symlink_to(disk)
    (cls / "sda1").symlink_to(disk / "sda1")
    assert st.parent_device("/dev/sda1", str(cls)) == "/dev/sda"
    assert st.parent_device("/dev/sda", str(cls)) == "/dev/sda"


def test_percent_like_df():
    # 100 GB, 5 GB reserviert: voll belegt = 95 used + 0 free -> 100 %
    assert st.Mount("/d", "/", "ext4", 100, 95, 0, False).percent == 100
