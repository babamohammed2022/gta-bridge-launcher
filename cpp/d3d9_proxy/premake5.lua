-- GTA Bridge d3d9 proxy (FusionFix pattern)
-- Builds d3d9.dll (x86) that forwards all D3D9 exports to vulkan.dll (DXVK)
-- when present, else the system d3d9.dll.
solution "gta_bridge_d3d9"
   configurations { "Debug", "Release" }
   platforms { "Win32" }
   location "build"

project "d3d9_proxy"
   language "C++"
   kind "SharedLib"
   targetdir "bin"
   targetname "d3d9"
   targetextension ".dll"
   staticruntime "On"

   files { "d3d9.def", "d3d9.cpp" }

   filter "configurations:Debug"
      defines { "DEBUG" }
      symbols "On"

   filter "configurations:Release"
      defines { "NDEBUG" }
      optimize "On"
