# Scripts

## Aurora

**Interactive Job**
```bash
qsub -l select=1 -l walltime=30:00 -l filesystems=flare -A <your_ProjectName> -q debug -I
```
