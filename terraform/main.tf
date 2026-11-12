# Define the AWS provider
provider "aws" {
  region = "eu-west-1"
}

# Create an EC2 instance
resource "aws_instance" "my_server" {
  ami           = "ami-xxxxxxxx"
  instance_type = "t2.micro"
}