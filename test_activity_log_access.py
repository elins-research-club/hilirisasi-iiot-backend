import crud


def test():
    assert crud.can_view_all_activity_logs(["view_all_logs"], "comp_ikea_id")
    assert crud.can_view_all_activity_logs(["view_all_nodes"], "comp_ikea_id")
    assert crud.can_view_all_activity_logs([], "comp_fmipa_ugm")
    assert not crud.can_view_all_activity_logs(["view_logs"], "comp_ikea_id")
    print("ok")


if __name__ == "__main__":
    test()
