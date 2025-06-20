def update_file_name_to_put_it_in_a_programmation_projet_folder(
    file, programmation_projet_id: int
):
    new_file_name = f"programmation_projet_{programmation_projet_id}/{file.name}"
    file.name = new_file_name
