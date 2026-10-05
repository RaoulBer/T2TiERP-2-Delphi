output "bucket" { value = var.bucket_name }
output "private_cidr" { value = var.private_cidr }
output "hosts" {
  value = { for role, node in google_compute_instance.node : role => {
    name = node.name
    ip   = node.network_interface[0].network_ip
    id   = node.instance_id
    role = local.nodes[role]
  } }
}
output "windows_image" { value = data.google_compute_image.windows.self_link }
