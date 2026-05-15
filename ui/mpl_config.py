def configure_matplotlib_fonts():
    """Configure matplotlib fonts for Chinese labels and minus signs."""
    import matplotlib

    matplotlib.rcParams["font.family"] = "sans-serif"
    matplotlib.rcParams["font.sans-serif"] = [
        "SimHei",
        "Microsoft YaHei",
        "STHeiti",
        "KaiTi",
        "FangSong",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    matplotlib.rcParams["axes.unicode_minus"] = False
