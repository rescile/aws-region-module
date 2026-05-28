{
  description = "AWS Deployment & Pulumi Graph Orchestration Environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
    in
    {
      devShells.${system}.default = pkgs.mkShell {
        buildInputs = [
          pkgs.awscli2
          # 1. The Pulumi CLI system tool binary
          pkgs.pulumi
          
          # 2. Python environment bundling both AWS SDKs and Pulumi SDKs
          (pkgs.python3.withPackages (ps: [
            ps.boto3
            ps.botocore
            ps.pulumi
            ps.pulumi-aws
          ]))
        ];

        shellHook = ''
          echo "☁️  AWS Python SDK & Pulumi Execution Layer Loaded"
          echo "Python version: $(python --version)"
          export AWS_DEFAULT_REGION="us-east-1"
          
          # NOTE ON VENV: If you use a local .venv, it will isolate itself 
          # from the Nix-provided python packages unless explicitly told to look outside.
          if [ ! -d ".venv" ]; then
            # --system-site-packages ensures it can see the Nix packages (pulumi, boto3)
            python -m venv --system-site-packages .venv
          fi
        '';
      };
    };
}
