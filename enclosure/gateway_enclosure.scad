// ============================================================================
// LoRaLAN WiFi Gateway enclosure (LoRa -> Wi-Fi -> MQTT) - shelf box, rev2
// Seeed XIAO ESP32-S3 (pin headers already soldered, pins down) + Wio-SX1262 stacked on top,
// USB-C wall power, SMA rod antenna on the lid via the 120 mm pigtail, XIAO 2.4 GHz FPC antenna
// (37 x 17.5, adhesive) stuck in a 0.3 mm locating recess on the inside of the front wall.
//
// rev2 vs rev1:
//   * The soldered headers ARE the mount: two floor rails with 2 x 7 pin holes (2.54 pitch, rows
//     15.24 apart) - the board presses in by its header pins, the header spacers seat on the rails.
//     Holes go through the floor so a paperclip can push the board out from underneath.
//     Optional variant sock="female": two cheap 1x7 female header strips glued into rail pockets.
//   * The rev1 corner pads / L brackets are gone (the pins locate the board).
//   * Box is taller (board sits 10.5 mm up instead of 5.0) and 2.5 mm longer (FPC needs a 40 mm wall).
//   * FPC gets a 0.3 mm deep locating recess on the front wall; the +X/-Y corner is open for its cable.
// Kept from rev1 / moisture rev6e: 2.5 walls, 2.0 lid, 6 mm rabbet, 0.45 snap bead, pry + fingernail
//   notches, SMA d6.5 hole + d12 boss in its own bay, USB-C 12.5 x 7.5 window, vents, solid back (keyholes optional: keyholes=true).
// Frame: X = long axis (USB-C end at -X), Y = across (-Y = front, +Y = back/wall side), Z = up.
//   Board STLs for the assembly views (not included; put your own in board_stl/) keep their X/Y, Z + brd_dz.
// Build:  openscad -o body.stl -D 'part="body"' gateway_enclosure.scad        (print upright, open top up)
//         openscad -o lid_print.stl -D 'part="lid_print"' gateway_enclosure.scad (top face on the bed)
//         add -D 'sock="female"' for the female-header variant (box grows 4 mm taller)
// Views:  part = "assembly" | "exploded" | "lidoff" | "section" | "coupon" (pin-hole test strip)
// ============================================================================
part = "body";
sock = "male";        // "male": pins press straight into printed holes | "female": glued 1x7 female strips
ant_len = 150;        // antenna rod above the hinge (views only)
$fn = 48;

/* [Proven moisture-enclosure numbers] */
wall      = 2.5;
clr       = 0.5;      // USB mouth -> inner wall
lid_t     = 2.0;
// ---- lid top text (engraved into the top face; reads right-way-up looking down on the lid, USB end at left)
lid_text       = "LoRaLAN WiFi GW";
lid_text_break = 7;        // char index where line 2 starts (-1 = one line). "LoRaLAN" | "WiFi GW"
lid_text_font  = "Liberation Sans:style=Bold";
lid_text_size  = 5.0;      // OpenSCAD size; cap height ~4.85 mm with this font
lid_text_mode  = "engrave";// "engrave" | "emboss" | "none"
lid_text_depth = 0.6;      // engrave depth (leaves 1.4 of the 2.0 lid); emboss height uses lid_text_raise
lid_text_raise = 0.5;
lid_text_l1_y  = -3.6;     // line-1 centre Y: band between the vent slots / SMA nut and the back edge
lid_text_l2_y  = -24.7;    // line-2 centre Y: band between the vent slots and the front edge
rabbet_h  = 6.0;
rabbet_t  = 1.25;
snap_bump = 0.45;     // continuous bead. Looser 0.35 if it's too stiff.
bead_z    = 2.0;
lid_fit   = 0.15;
ant_d     = 6.5;      // SMA bulkhead 1/4-36
ant_boss_d= 12; ant_boss_h = 1.0;
ant_keepout_d = 10; ant_keepout_h = 10;
e_pry_w = 6.0; e_pry_h = 1.3; e_pry_d = 0.7;

/* [Header pins - measure yours] */
pin_len    = 6.0;     // exposed male pin below the black plastic spacer (measured 6.0)
spacer_h   = 2.5;     // black plastic spacer height (standard 2.5)
pin_w      = 0.64;    // square pin (diagonal 0.905)
pin_clr    = 0.10;    // hole = pin diagonal + pin_clr  -> d 1.005 nominal; FDM prints ~0.1-0.15 small = snug
pin_hole_d = pin_w*sqrt(2) + pin_clr;
pin_chamf  = 0.4;     // lead-in chamfer at the top of every hole
pitch      = 2.54;
pin_x0     = 2.77;    // first pin (USB end), measured from the XIAO STEP castellation holes
pin_rows_y = [-22.225, -6.985];   // 15.24 apart
rail_w     = 4.0;     // rail under each 2.54 spacer strip
pin_tip_clr = 0.5;    // pin tip stops this far above the floor top -> pins never bottom out, the spacer always seats
sock_h     = pin_len + pin_tip_clr;   // male rail height above the floor (6.5)
sock_through = true;  // holes continue through the floor (push-out holes; also +2 mm tolerance for longer pins)
/* [Female-header variant] */
fem_h      = 8.5;     // 1x7 female header housing height (standard 8.5)
fem_w      = 2.54; fem_l = 7*pitch;
fem_clr    = 0.15;    // per side, pocket around the housing (glue it: CA / epoxy)
fem_rail_h = 3.0;     // rail height above the floor
fem_pocket = 1.5;     // pocket depth into the rail (locates the strip)
fem_tail_d = 1.3;     // through holes for the 3 mm solder tails

/* [Gateway] */
floor_t   = 2.0;
fit       = 0.35;     // board <-> lid hold-down clearance
back_t    = 6.5;      // back (+Y) wall: solid by default (shelf unit); 6.5 kept so the lid text/size stay put
keyholes  = false;    // sits on a shelf, no wall mount. true = keyhole slots in the back wall
feet      = false;    // optional rubber-bumper recesses in the bottom (flat bottom by default)
foot_d    = 6.5; foot_h = 0.8;   // fits 6.4 mm self-adhesive bumpers; 1.2 of the 2.0 floor remains
usb_w = 12.5; usb_h = 7.5; usb_r = 2.0;
ufl_cable = 2.0;
fpc_l = 37.4; fpc_w = 17.5; fpc_rec = 0.3; fpc_rec_clr = 0.3;   // FPC antenna 37 x 17.5 (A-02 is 37.4)

// board extents (STL frame, measured from the STEP)
xiao_x = [-0.15, 20.80]; xiao_y = [-23.50, -5.72]; xiao_z = [1.60, 2.85];
car_x  = [-0.15, 21.29]; car_z  = [6.34, 7.94];
mod_x  = [9.37, 20.97];  mod_y  = [-20.11, -9.11]; mod_top = 10.14;
usb_mouth_x = -1.68; usb_cy = -14.61; usb_cz = 4.45;
lora_ufl = [19.3, -11.1, 9.24];
led_xy   = [7.97, -18.92];
pins_x   = [for (i=[0:6]) pin_x0 + i*pitch];

// ---- stack height
rail_top  = floor_t + (sock=="female" ? fem_rail_h : sock_h);
fem_bot   = rail_top - fem_pocket;
seat_z    = sock=="female" ? fem_bot + fem_h : rail_top;     // header spacer bottom rests here
xiao_bot  = seat_z + spacer_h;                               // male: 11.0   female: 14.5
brd_dz    = xiao_bot - xiao_z[0];

// ---- enclosure
in_x0 = usb_mouth_x - clr;                 // -2.18
ant_x = car_x[1] + 3.0 + ant_keepout_d/2;  // 29.29 : SMA bay beside the board
in_x1 = ant_x + ant_keepout_d/2 + 3.2 + 2.5;  // 39.99 : +2.5 vs rev1 so the front wall is 42 mm long inside
in_y0 = -26.55;                            // same width as rev1
in_y1 = xiao_y[1] + 2.0;                   // -3.72
ant_y = (in_y0 + in_y1)/2;
out_x0 = in_x0 - wall; out_x1 = in_x1 + wall;
out_y0 = in_y0 - wall; out_y1 = in_y1 + back_t;
H     = xiao_bot + 16.5;                   // male 27.5 / female 31.0 (rev1 20.5 = xiao_bot 5.0 + 15.5, +1 for the FPC)
peg_z0  = car_z[1] + brd_dz + fit;
pegs = [[2.2,-7.4],[2.2,-21.8],[15.0,-7.25],[15.0,-21.95]];
// FPC recess on the inner face of the front wall: X toward the +X end (away from USB), Z under the rabbet
fpc_rx = [in_x1 - 1.0 - (fpc_l + 2*fpc_rec_clr), in_x1 - 1.0];
fpc_rz = [floor_t + 0.4, floor_t + 0.4 + fpc_w + 2*fpc_rec_clr];
assert(fpc_rz[1] <= H - rabbet_h - 0.3, "FPC recess runs into the lid rabbet");

module rbox(p0, p1, r=1) hull() for (x=[p0[0]+r, p1[0]-r], y=[p0[1]+r, p1[1]-r])
    translate([x,y,p0[2]]) cylinder(r=r, h=p1[2]-p0[2]);
module cube2(p0,p1){ translate(p0) cube([p1[0]-p0[0],p1[1]-p0[1],p1[2]-p0[2]]); }
module tear2d(d) hull() { circle(d=d); translate([0, d/2*sqrt(2)]) circle(d=0.01); }

module snap_bumps(grow=0) {
    zc = H - rabbet_h + bead_z; b = snap_bump + grow; e = 0.01;
    x0=out_x0+rabbet_t; x1=out_x1-rabbet_t; y0=out_y0+rabbet_t; y1=out_y1-rabbet_t;
    difference() {
        for (s=[-1,1]) hull() {
            translate([0,0,zc]) rbox([x0-b,y0-b,0],[x1+b,y1+b,e], r=1.5+b);
            translate([0,0,zc+s*(b+0.01)-(s<0?0:e)]) rbox([x0-0.01,y0-0.01,0],[x1+0.01,y1+0.01,e], r=1.5);
        }
        translate([0,0,-1]) rbox([in_x0,in_y0,0],[in_x1,in_y1,H+5], r=0.6);
    }
}

// ---- pin socket: two rails, one under each header row
rail_x = [pins_x[0] - pitch/2 - 1.0, pins_x[6] + pitch/2 + 1.0];    // 0.50 .. 20.28
module rails() for (y=pin_rows_y)
    cube2([rail_x[0], y-rail_w/2, floor_t-0.01], [rail_x[1], y+rail_w/2, rail_top]);
module pin_holes() for (y=pin_rows_y, x=pins_x) translate([x, y, 0]) {
    if (sock=="male") {
        translate([0,0,sock_through ? -1 : rail_top-pin_len-pin_tip_clr]) cylinder(d=pin_hole_d, h=rail_top+2, $fn=24);  // through (push-out) or blind
        translate([0,0,rail_top-pin_chamf]) cylinder(d1=pin_hole_d, d2=pin_hole_d+2*pin_chamf, h=pin_chamf+0.01, $fn=24);
    } else {
        translate([0,0,-1]) cylinder(d=fem_tail_d, h=rail_top+2, $fn=24);               // solder tails
    }
}
module fem_pockets() if (sock=="female") for (y=pin_rows_y)
    translate([(pins_x[0]+pins_x[6])/2, y, fem_bot + 50]) cube([fem_l+2*fem_clr, fem_w+2*fem_clr, 100], center=true);

// ---- keyholes in the back wall (box hangs lid-up, antenna vertical). #6/#8 or M3.5/M4 pan head
kh_x = [5.0, 30.0];
kh_entry_d = 8.6; kh_slot_w = 4.4; kh_lip = 2.0; kh_cham = 3.2;
kh_z0 = 5.2; kh_travel = 6.3;
kh_ztop = H - rabbet_h - 0.5;
module keyholes() intersection() {
  translate([-50,-50,-1]) cube([200,100,kh_ztop+1]);
  for (x=kh_x) translate([x, 0, 0]) {
    translate([0, out_y1+1, kh_z0]) rotate([90,0,0]) linear_extrude(kh_lip+kh_cham+1) circle(d=kh_entry_d);
    translate([0, out_y1+1, 0]) rotate([90,0,0]) linear_extrude(kh_lip+1.01)
        hull() { translate([0,kh_z0]) circle(d=kh_slot_w); translate([0,kh_z0+kh_travel]) tear2d(kh_slot_w); }
    translate([0, out_y1-kh_lip, 0]) rotate([90,0,0]) linear_extrude(kh_cham)
        hull() { translate([0,kh_z0]) circle(d=kh_entry_d); translate([0,kh_z0+kh_travel]) tear2d(kh_entry_d); }
}}

foot_xy = [for (x=[out_x0+4.0, out_x1-4.0], y=[out_y0+4.0, out_y1-4.0]) [x,y]];
module foot_recesses() for (p=foot_xy) translate([p[0],p[1],-0.01]) cylinder(d=foot_d, h=foot_h+0.01, $fn=48);

// ---- vents
end_slots_y = [-23.5, -19.5, -15.5, -11.5, -7.5];        // +X end wall, 9 mm tall, top 2 mm under the rabbet
end_vent_z0 = H - rabbet_h - 2.0 - 9.0;
lid_slots = [[5.0,-20.0,-9.9],[led_xy[0],-20.0,-9.9],[11.4,-20.0,-9.9],[15.0,-18.9,-10.4]];  // X 7.97 over the Wio LED
module end_vents() for (y=end_slots_y)
    translate([in_x1-1, y-0.8, end_vent_z0]) cube([wall+2, 1.6, 9.0]);
module lid_vents() for (v=lid_slots)
    translate([v[0], 0, H-ant_boss_h-1]) hull() for (y=[v[1], v[2]]) translate([0,y,0]) cylinder(d=1.6, h=lid_t+ant_boss_h+2, $fn=24);

module usb_cut() translate([out_x0-1, usb_cy, usb_cz+brd_dz]) rotate([0,90,0])
    linear_extrude(usb_mouth_x - 0.1 - out_x0 + 1)
        offset(r=usb_r) square([usb_h-2*usb_r, usb_w-2*usb_r], center=true);

module fpc_recess() cube2([fpc_rx[0], in_y0 - fpc_rec, fpc_rz[0]], [fpc_rx[1], in_y0 + 0.01, fpc_rz[1]]);

// ---------------------------------------------------------------- body
module body() difference() {
    union() {
        difference() {
            rbox([out_x0,out_y0,0],[out_x1,out_y1,H], r=2.5);
            rbox([in_x0,in_y0,floor_t],[in_x1,in_y1,H+1], r=0.6);
            difference() {
                translate([0,0,H-rabbet_h]) rbox([out_x0-1,out_y0-1,0],[out_x1+1,out_y1+1,rabbet_h+1], r=1);
                translate([0,0,H-rabbet_h-1]) rbox([out_x0+rabbet_t,out_y0+rabbet_t,0],[out_x1-rabbet_t,out_y1-rabbet_t,rabbet_h+2], r=1.5);
            }
        }
        snap_bumps();
        rails();
    }
    pin_holes();
    fem_pockets();
    usb_cut();
    end_vents();
    if (keyholes) keyholes();
    if (feet) foot_recesses();
    fpc_recess();
}

// ---------------------------------------------------------------- lid (rev1 lid, taller skirt position follows H)
module lid() difference() {
    union() {
        translate([0,0,H]) rbox([out_x0,out_y0,0],[out_x1,out_y1,lid_t], r=2.5);
        difference() {
            translate([0,0,H-rabbet_h]) rbox([out_x0,out_y0,0],[out_x1,out_y1,rabbet_h+0.01], r=2.5);
            translate([0,0,H-rabbet_h-1]) rbox([out_x0+rabbet_t-lid_fit,out_y0+rabbet_t-lid_fit,0],
                                               [out_x1-rabbet_t+lid_fit,out_y1-rabbet_t+lid_fit,rabbet_h+1.5], r=1.5);
        }
        translate([ant_x, ant_y, H-ant_boss_h]) cylinder(d=ant_boss_d, h=ant_boss_h+0.01);
        for (p=pegs) translate([p[0], p[1], peg_z0]) cylinder(d=3.0, h=H-peg_z0+0.01);   // hold-downs over the carrier
    }
    translate([ant_x, ant_y, H-ant_boss_h-1]) cylinder(d=ant_d, h=lid_t+ant_boss_h+2);
    snap_bumps(grow=0.15);
    lid_vents();
    translate([(out_x0+out_x1)/2-e_pry_w/2, out_y0-1, H-rabbet_h-1]) cube([e_pry_w, e_pry_d+1, 1+e_pry_h]);
    translate([out_x1-0.6, ant_y-4, H-rabbet_h-0.01]) cube([1, 8, 1.2]);
    if (lid_text_mode=="engrave") translate([0,0,H+lid_t-lid_text_depth]) linear_extrude(lid_text_depth+1) lid_text_2d();
}
function substr(s,a,b) = a>=b ? "" : str(s[a], substr(s,a+1,b));
lid_text_x = (out_x0+out_x1)/2;
module lid_text_2d() {
    n = len(lid_text);
    l1 = lid_text_break<0 ? lid_text : substr(lid_text, 0, lid_text_break);
    l2 = lid_text_break<0 ? "" : substr(lid_text, lid_text_break + (lid_text[lid_text_break]==" " ? 1 : 0), n);
    for (l=[[l1, lid_text_break<0 ? (lid_text_l1_y+lid_text_l2_y)/2 : lid_text_l1_y], [l2, lid_text_l2_y]]) if (len(l[0])>0)
        translate([lid_text_x, l[1]]) text(l[0], size=lid_text_size, font=lid_text_font, halign="center", valign="center");
}
module lid_full() { lid(); if (lid_text_mode=="emboss") translate([0,0,H+lid_t-0.01]) linear_extrude(lid_text_raise+0.01) lid_text_2d(); }

// ---- pin-hole test coupon: 3 rows x 7 holes, d = nominal -0.1 / nominal / +0.1 (print it first)
module coupon() difference() {
    cube2([0, 0, 0], [7*pitch+3, 3*4.0+1, sock_h]);   // coupon: 6.5 thick, through holes
    for (r=[0:2], i=[0:6]) translate([1.5+pitch/2+i*pitch, 2.5+r*4.0, -1]) {
        cylinder(d=pin_hole_d-0.1+0.1*r, h=sock_h+2, $fn=24);
        translate([0,0,sock_h+1-pin_chamf]) cylinder(d1=pin_hole_d-0.1+0.1*r, d2=pin_hole_d-0.1+0.1*r+2*pin_chamf, h=pin_chamf+0.01, $fn=24);
    }
    for (r=[0:2]) translate([0.4, 2.5+r*4.0, sock_h-0.4]) linear_extrude(1) text(str(r), size=1.6, valign="center");
}

// ---------------------------------------------------------------- models for views / checks
S = "board_stl/";     // board models for the assembly views only (not included)
module header() color([0.08,0.08,0.08]) for (y=pin_rows_y) {      // soldered male header, pins down
    translate([(pins_x[0]+pins_x[6])/2, y, xiao_bot-spacer_h/2]) cube([7*pitch-0.05, 2.5, spacer_h], center=true);
}
module header_pins() color("gold") for (y=pin_rows_y, x=pins_x)
    translate([x, y, xiao_bot - spacer_h - pin_len + (pin_len+spacer_h)/2]) cube([pin_w, pin_w, pin_len+spacer_h], center=true);
module fem_strips() if (sock=="female") color([0.1,0.1,0.1]) for (y=pin_rows_y)
    translate([(pins_x[0]+pins_x[6])/2, y, fem_bot+fem_h/2]) difference() {
        cube([fem_l, fem_w, fem_h], center=true);
        for (x=pins_x) translate([x-(pins_x[0]+pins_x[6])/2, 0, 0]) cube([1.0,1.0,fem_h+1], center=true);
    }
module board() {
    translate([0,0,brd_dz]) {
        color("dimgray")   import(str(S,"xiao_board.stl"));
        color("silver")    import(str(S,"xiao_usb_c.stl"));
        color("gold")      import(str(S,"xiao_wifi_ufl.stl"));
        color("navy")      import(str(S,"wio_carrier.stl"));
        color("lightgray") import(str(S,"wio_sx1262_module.stl"));
        color("gold") translate([lora_ufl[0], lora_ufl[1], lora_ufl[2]-1.25]) cylinder(d=2.6, h=1.25+ufl_cable);
    }
    header(); header_pins(); fem_strips();
}
module sma() color("gold") translate([ant_x, ant_y, 0]) {
    translate([0,0,H-ant_keepout_h+2]) cylinder(d=6.3, h=ant_keepout_h-2+lid_t+6);
    translate([0,0,H-ant_boss_h-2]) cylinder(d=8/cos(30), h=2, $fn=6);
    translate([0,0,H+lid_t]) cylinder(d=8/cos(30), h=2, $fn=6);
}
module antenna() color([0.15,0.15,0.15]) translate([ant_x, ant_y, H+lid_t+6]) {
    cylinder(d=9, h=12); translate([0,0,12]) cylinder(d1=9, d2=7, h=6); translate([0,0,18]) cylinder(d=7, h=ant_len);
}
// FPC (0.2 thick) stuck in the recess, centred
module fpc() color([0.12,0.12,0.14])
    cube2([fpc_rx[0]+fpc_rec_clr, in_y0-fpc_rec, fpc_rz[0]+fpc_rec_clr], [fpc_rx[1]-fpc_rec_clr, in_y0-fpc_rec+0.2, fpc_rz[1]-fpc_rec_clr]);
module usb_plug() color([0.1,0.1,0.1]) translate([usb_mouth_x, usb_cy, usb_cz+brd_dz]) {
    translate([-0.01,0,0]) rotate([0,-90,0]) linear_extrude(6.6) offset(r=1.2) square([0.0001, 8.34-2.4], center=true);
    translate([-0.6,0,0]) rotate([0,-90,0]) linear_extrude(22) offset(r=1.5) square([6.4-3, 11.6-3], center=true);
}

cB = [0.95,0.55,0.15]; cL = [0.55,0.25,0.08];
if (part=="body") body();
if (part=="lid")  lid_full();
if (part=="lid_print") translate([0,0,H+lid_t]) rotate([180,0,0]) lid_full();   // top face on the bed; rotate, never mirror
if (part=="coupon") coupon();
if (part=="board") board();
if (part=="pins") header_pins();
if (part=="spacers") header();
if (part=="sma") sma();
if (part=="fpc") fpc();
if (part=="assembly") { color(cB) body(); color(cL) lid_full(); board(); sma(); antenna(); usb_plug(); }
if (part=="exploded") { color(cB) body(); translate([0,0,62]) { color(cL) lid_full(); sma(); antenna(); } translate([0,0,30]) board(); fpc(); }
if (part=="usbview")  { color(cB) body(); color(cL) lid_full(); board(); sma(); antenna(); }
if (part=="fpcwall")  { intersection() { color(cB) body(); translate([-50,-60,-1]) cube([150, 60+pin_rows_y[0]+3, 60]); } fpc(); color("silver") translate([fpc_rx[1]-6, in_y0-0.1+0.2, fpc_rz[0]+9]) rotate([-90,0,0]) cylinder(d=2.0,h=0.6); }
if (part=="lidoff")   { color(cB) body(); board(); fpc(); }
if (part=="section")  intersection() { union() { color(cB) body(); board(); fpc(); }
                                       translate([-50, pin_rows_y[0]-50, -5]) cube([100, 50, 60]); }
echo(str("OUTSIDE ", out_x1-out_x0, " x ", out_y1-out_y0, " x ", H+lid_t, " | inside ", in_x1-in_x0, " x ", in_y1-in_y0, " x ", H-floor_t,
         " | sock ", sock, " rail_top ", rail_top, " xiao_bot ", xiao_bot, " brd_dz ", brd_dz, " usb_cz ", usb_cz+brd_dz,
         " | hole_d ", pin_hole_d, " | fpc recess X ", fpc_rx, " Z ", fpc_rz, " | ant ", ant_x, ",", ant_y, " peg_z0 ", peg_z0,
         " | out x ", out_x0, "..", out_x1, " y ", out_y0, "..", out_y1));
if (part=="lidtext") translate([0,0,H+lid_t-lid_text_depth]) linear_extrude(lid_text_depth) lid_text_2d();
if (part=="lidkeep") { lid_vents(); translate([ant_x, ant_y, H]) cylinder(d=8/cos(30), h=lid_t+2, $fn=6); }   // vent slots + SMA nut
if (part=="lidtop")  { color(cL) lid_full(); sma(); if (lid_text_mode=="engrave") color("white") translate([0,0,H+lid_t-lid_text_depth]) linear_extrude(0.05) lid_text_2d(); }   // white = engraving floor (render aid only)
